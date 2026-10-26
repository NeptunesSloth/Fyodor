"""Wave 110J final pass, real Oracle text. Every scenario ends with replay + save/load.

* Enduring Angel: 614.1a the life-total reduction to 0 or less (damage 120.3a, life loss 119.3) is replaced: it transforms (701.28), life becomes 3
  (119.5); a token or non-double-faced copy cannot, so its controller loses the game (ruling 2015-06-22).
* Aegis of the Legion: 702.134c the equipped creature "mentors" a creature when its mentor ability (granted by the Aegis) resolves with that
  creature as target: the shield counter goes on it; nothing when the target's power is no longer lower at resolution (ruling 2018-07-13).
* Silhouette: 615.1 / 115.1 damage a spell or ability that targets the creature would cause is prevented this turn; other damage is not.
* Lost in Thought: 508.1c / 602.5 the Aura stops attacks and activations; its controller exiles three cards from their graveyard (special action, ruling
  2018-04-27; here an ability, the Volrath's Curse ceiling) to ignore it until end of turn.
* Defensive Formation: 510.1a the defending player (its controller) assigns combat damage of each creature attacking them, trample choices included
  (ruling 2014-04-26); a creature attacking someone else is still assigned by its controller.
* Gluttonous Hellkite: 603.3 / 107.3i the cast trigger has each player sacrifice X creatures before the spell resolves; it then enters with two +1/+1
  counters per creature actually sacrificed (not X, ruling 2014-07-18); a countered spell enters with none.
* Ogre Battlecaster: 608.2g the cast (paying {R}{R} more, 118.8) is made as the attack trigger resolves; the spell is exiled instead of going to the graveyard;
  603.7a "when you cast that spell" pumps the Ogre by its mana value; nothing is gained when no cast is made.
* Emblazoned Golem: 601.2h X is paid only with colored mana, at most one of each color (kicker {X}, counters per X); unkicked, nothing is restricted.
* Garth One-Eye: 707.12 a copy of the card with a chosen name (only the listed names, each Garth remembering its own: rulings 2017-03-14) is made and may be cast,
  its costs paid; declining to cast it still uses the name up.
* Phylactery Lich: 614.12a / 614.1c the artifact is chosen as it enters (no target, ruling 2013-04-15), the counter goes on it; with no artifact
  nothing happens and the state trigger (603.8) sacrifices the Lich; another phylactery counter anywhere keeps it.
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card
from tests.game_helpers import act
from tests.wave9c_kit import build, life, mana, to_hand
from tests.wave110j_kit import (  # noqa: F401
    EXTRA,
    ability,
    card_db,
    check,
    full,
    hand_new,
    now,
    put_new,
    settle,
    to_phase,
)

PLAIN = "Plain Angel"  # a single-faced permanent with Enduring Angel's replacement text (what a copy of it is, ruling 2015-06-22)
EXTRA.append(card(PLAIN, set_code="w110j", number="F001", mana_cost="{2}{W}{W}", cmc=4.0, type_line="Creature — Angel", power="3", toughness="3", colors=["W"],
                  color_identity=["W"], keywords=[], layout="normal", oracle_text="If your life total would be reduced to 0 or less, instead transform this creature "
                  "and your life total becomes 3. Then if this creature didn't transform this way, you lose the game."))
LICH, ORNI = "Phylactery Lich", "Ornithopter"
ANGEL, BOLT, BLOOD = "Enduring Angel // Angelic Enforcer", "Lightning Bolt", "Sign in Blood"


@pytest.mark.parametrize("name", [LICH, ANGEL])
def test_full(cards, name):
    from app.rules import coverage

    cov = coverage.of_card_data(cards.resolve(name))
    assert cov.level == "FULL", [f for f in cov.features if not f.supported]


def test_lich_counter_on_chosen_artifact_and_it_stays(cards):
    s = build(cards, [LICH, ORNI], [], forests=30, islands=30)
    orni = put_new(s, ORNI)
    lich = hand_new(s, LICH)
    from tests.wave110j_kit import cost

    mana(s, "p1", **cost(LICH))
    act(s, "p1", type="cast_spell", card_id=lich.id)
    settle(s)
    assert now(s, orni).counters.get("phylactery") == 1
    assert now(s, lich).zone.endswith(":battlefield")
    check(s)


def test_lich_without_an_artifact_is_sacrificed(cards):
    s = build(cards, [LICH], [], forests=30, islands=30)
    lich = hand_new(s, LICH)
    from tests.wave110j_kit import cost

    mana(s, "p1", **cost(LICH))
    act(s, "p1", type="cast_spell", card_id=lich.id)
    settle(s)
    assert now(s, lich).zone.endswith(":graveyard")
    check(s)


def _hit(s, name, target="p1"):
    from tests.wave110j_kit import cast_on

    return cast_on(s, name, target)


@pytest.mark.parametrize("spell", [BOLT, BLOOD])
def test_angel_replaces_a_lethal_reduction(cards, spell):
    """Lightning Bolt (damage) and Sign in Blood (life loss, 3 life lost is not enough: life 2) both reduce p1 to 0 or less."""
    s = build(cards, [ANGEL, BOLT, BLOOD], [], forests=30, islands=30)
    angel = put_new(s, ANGEL)
    act(s, "p1", type="set_life", player="p1", value=2 if spell == BLOOD else 3)
    _hit(s, spell)
    assert life(s, "p1") == 3
    assert now(s, angel).face == 1 and now(s, angel).zone.endswith(":battlefield")
    assert not s.state.rules.lost
    check(s)


def test_angel_does_nothing_for_a_nonlethal_reduction(cards):
    s = build(cards, [ANGEL, BOLT], [], forests=30, islands=30)
    angel = put_new(s, ANGEL)
    _hit(s, BOLT)
    assert life(s, "p1") == 37 and now(s, angel).face == 0
    check(s)


def test_a_single_faced_angel_cannot_transform_so_its_controller_loses(cards):
    s = build(cards, [PLAIN, BOLT], [], forests=30, islands=30)
    angel = put_new(s, PLAIN)
    act(s, "p1", type="set_life", player="p1", value=3)
    _hit(s, BOLT)
    assert now(s, angel).face == 0 and "p1" in s.state.rules.lost
    check(s)


AEGIS, ELVES, BEARS = "Aegis of the Legion", "Llanowar Elves", "Grizzly Bears"


def growth_id(s):
    return next(c.id for c in s.state.cards.values() if c.name == "Giant Growth" and c.zone == "p1:hand")


def _mentor_attack(cards, *, growth=False):
    from tests.wave110j_kit import mana

    s = build(cards, [AEGIS, BEARS, ELVES, "Giant Growth"], [], forests=30, islands=30)
    aegis, bears, elves = put_new(s, AEGIS), put_new(s, BEARS), put_new(s, ELVES)
    to_phase(s, "main1", turn=3)
    mana(s, "p1", **{"C": 3})
    act(s, "p1", type="activate_ability", card_id=aegis.id, ability=ability(s, aegis, "Equip {3}"), targets=[bears.id])
    settle(s)
    assert now(s, aegis).attached_to == bears.id
    if growth:
        to_hand(s, "Giant Growth")
        put_new(s, "Forest")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}, {"card_id": elves.id, "target": "p2"}])
    return s, bears, elves


def test_aegis_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(AEGIS)).level == "FULL"


def test_aegis_puts_a_shield_counter_on_the_mentored_creature(cards):
    s, bears, elves = _mentor_attack(cards)
    settle(s)  # mentor targets the creature with lesser power (Elves 1 < Bears 3), then the Aegis trigger
    assert now(s, elves).counters.get("+1/+1") == 1 and now(s, elves).counters.get("shield") == 1
    assert not now(s, bears).counters.get("shield")
    check(s)


def test_aegis_gives_no_shield_when_the_target_is_no_longer_lesser_at_resolution(cards):
    """Ruling 2018-07-13: the mentor ability does nothing once the target's power is not lower, so the equipped creature did not mentor it."""
    s, bears, elves = _mentor_attack(cards, growth=True)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[elves.id])  # mentor's target (the only legal one)
    act(s, "p1", type="cast_spell", card_id=growth_id(s), targets=[elves.id])  # in response: Elves 4/4, no longer less than Bears' 3
    settle(s)
    assert not now(s, elves).counters.get("+1/+1") and not now(s, elves).counters.get("shield")
    check(s)


SIL, PYRO, SORC = "Silhouette", "Pyroclasm", "Prodigal Sorcerer"


def _silhouetted(cards):
    from tests.wave110j_kit import cast_on

    s = build(cards, [SIL, BOLT, PYRO, BEARS, SORC], [BEARS], forests=30, islands=30)
    bears, other, sorc = put_new(s, BEARS), put_new(s, BEARS, "p2"), put_new(s, SORC)
    to_phase(s, "main1", turn=3)
    cast_on(s, SIL, bears)
    return s, bears, other, sorc


def test_silhouette_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(SIL)).level == "FULL"


def test_silhouette_prevents_damage_of_a_spell_that_targets_it(cards):
    from tests.wave110j_kit import cast_on

    s, bears, other, _ = _silhouetted(cards)
    cast_on(s, BOLT, bears)
    assert now(s, bears).damage == 0 and now(s, bears).zone.endswith(":battlefield")
    cast_on(s, BOLT, other)  # not the chosen creature
    assert now(s, other).zone.endswith(":graveyard")
    check(s)


def test_silhouette_does_not_stop_damage_from_a_spell_that_does_not_target_it(cards):
    from tests.wave110j_kit import cast_on

    s, bears, other, _ = _silhouetted(cards)
    cast_on(s, PYRO)
    assert now(s, bears).zone.endswith(":graveyard")
    check(s)


def test_silhouette_prevents_damage_of_an_ability_that_targets_it(cards):
    from tests.wave110j_kit import ability

    s, bears, other, sorc = _silhouetted(cards)
    act(s, "p1", type="activate_ability", card_id=sorc.id, ability=ability(s, sorc, "{T}"), targets=[bears.id])
    settle(s)
    assert now(s, sorc).tapped and now(s, bears).damage == 0
    check(s)


LOST = "Lost in Thought"


def _lost_turn(cards, graveyard):
    from tests.wave110j_kit import cast_on, grave_new

    s = build(cards, [LOST], [BEARS, BEARS, BEARS, BEARS, BEARS, BEARS], forests=30, islands=30)
    bears = put_new(s, BEARS, "p2")
    for _ in range(graveyard):
        grave_new(s, BEARS, "p2")
    cast_on(s, LOST, bears)
    act(s, "p2", type="set_stops", own=["declare_attackers"])
    to_phase(s, "main1", turn=2)
    return s, bears


def _to_declare(s):
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
        if s.state.turn.phase not in ("main1", "beginning_of_combat", "declare_attackers"):
            break


def test_lost_in_thought_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(LOST)).level == "FULL"


def test_lost_in_thought_stops_attacks(cards):
    from app.game.errors import ActionError

    s, bears = _lost_turn(cards, 0)
    act(s, "p2", type="pass_priority")
    _to_declare(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)


def test_lost_in_thought_is_ignored_by_exiling_three_cards_from_the_graveyard(cards):
    from tests.wave110j_kit import ability

    s, bears = _lost_turn(cards, 3)
    act(s, "p2", type="activate_ability", card_id=bears.id, ability=ability(s, bears, "Exile three cards from your graveyard"))
    settle(s)
    assert len([c for c in s.state.cards.values() if c.owner == "p2" and c.zone.endswith(":exile")]) == 3
    _to_declare(s)
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])
    check(s)


def test_lost_in_thought_needs_three_cards(cards):
    from app.game.errors import ActionError
    from tests.wave110j_kit import ability

    s, bears = _lost_turn(cards, 2)
    with pytest.raises(ActionError):
        act(s, "p2", type="activate_ability", card_id=bears.id, ability=ability(s, bears, "Exile three cards from your graveyard"))
    check(s)


DF, GIANT, TRAMPLER = "Defensive Formation", "Hill Giant", "Garruk's Companion"


def _blocked(cards, attacker, formation=True, both=True):
    s = build(cards, [attacker], [DF, BEARS, BEARS] if formation else [BEARS, BEARS], forests=30, islands=30)
    att = put_new(s, attacker)
    if formation:
        put_new(s, DF, "p2")
    b1, b2 = put_new(s, BEARS, "p2"), put_new(s, BEARS, "p2")
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": att.id, "target": "p2"}])
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    act(s, "p2", type="declare_blockers", blocks=[{"blocker_id": b.id, "attacker_id": att.id} for b in ((b1, b2) if both else (b1,))])
    return s, att, b1, b2


def test_defensive_formation_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(DF)).level == "FULL"


def test_defender_divides_the_damage_of_an_attacker_blocked_twice(cards):
    s, att, b1, b2 = _blocked(cards, GIANT)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p2"  # 510.1a, Defensive Formation: not the attacking player
    check(s)


def test_defender_may_put_all_the_damage_on_one_blocker(cards):
    s, att, b1, b2 = _blocked(cards, GIANT)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2"
    act(s, "p2", type="choose", decision_id=d.id, amounts=[3 if o.id == b2.id else 0 for o in d.options])
    settle(s)
    assert now(s, b2).zone.endswith(":graveyard") and not now(s, b1).damage
    check(s)


def test_defender_decides_how_much_trample_damage_reaches_them(cards):
    s, att, b1, b2 = _blocked(cards, TRAMPLER, both=False)
    d = None
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d is not None and d.player == "p2"  # ruling: the trample choice is the defender's
    act(s, "p2", type="choose", decision_id=d.id, amounts=[3 if o.id == b1.id else 0 for o in d.options])
    settle(s)
    assert life(s, "p2") == 40
    check(s)


def test_without_the_formation_the_attacker_divides(cards):
    s, att, b1, b2 = _blocked(cards, GIANT, formation=False)
    for _ in range(20):
        d = s.state.rules.decision
        if d is not None and d.kind == "divide":
            break
        act(s, s.state.rules.priority, type="pass_priority")
    assert d.player == "p1"
    check(s)


HELL = "Gluttonous Hellkite"


def _hellkite(cards, x, mine, theirs):
    from tests.wave110j_kit import mana

    s = build(cards, [HELL, *([BEARS] * mine)], [BEARS] * theirs, forests=30, islands=30)
    for _ in range(mine):
        put_new(s, BEARS)
    for _ in range(theirs):
        put_new(s, BEARS, "p2")
    spell = to_hand(s, HELL)
    mana(s, "p1", B=1, R=1, G=1, C=2 * x)
    act(s, "p1", type="cast_spell", card_id=spell.id, x_value=x)
    return s, spell


def test_hellkite_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(HELL)).level == "FULL"


def test_hellkite_enters_with_two_counters_per_creature_sacrificed(cards):
    """X=2: p1 has one creature (sacrifices it), p2 has three and chooses two: three sacrificed in all, six counters."""
    s, spell = _hellkite(cards, 2, 1, 3)
    settle(s)
    assert len([c for c in s.state.cards.values() if c.name == BEARS and c.zone.endswith(":graveyard")]) == 3
    assert now(s, spell).zone.endswith(":battlefield") and now(s, spell).counters.get("+1/+1") == 6
    check(s)


def test_hellkite_with_no_creatures_to_sacrifice_enters_without_counters(cards):
    s, spell = _hellkite(cards, 1, 0, 0)
    settle(s)
    assert now(s, spell).zone.endswith(":battlefield") and not now(s, spell).counters.get("+1/+1")
    check(s)


OGRE = "Ogre Battlecaster"


def _ogre(cards, mountains=3):
    from tests.wave110j_kit import grave_new

    s = build(cards, [OGRE, BOLT, *["Mountain"] * mountains], [], forests=30, islands=30)
    ogre = put_new(s, OGRE)
    for _ in range(mountains):
        put_new(s, "Mountain")
    bolt = grave_new(s, BOLT)
    to_phase(s, "declare_attackers", turn=3)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ogre.id, "target": "p2"}])
    return s, ogre, bolt


def test_ogre_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(OGRE)).level == "FULL"


def test_ogre_casts_the_spell_for_rr_more_exiles_it_and_gets_plus_mana_value(cards):
    from tests.wave110j_kit import ch

    s, ogre, bolt = _ogre(cards)
    for _ in range(8):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"] if "p2" in [o.id for o in d.options] else [o.id for o in d.options][: max(1, d.min_choices)])
    assert now(s, bolt).zone.endswith(":exile")  # "exile it instead" of the graveyard
    assert life(s, "p2") == 40 - 3 - 4  # Bolt, then the Ogre unblocked as a 4/3
    assert ch(s, ogre).pt == (3 + 1, 3)  # +1/+0: Lightning Bolt's mana value is 1 (Ogre is 3/3)
    assert not [c for c in s.state.cards.values() if c.name == "Mountain" and c.zone.endswith(":battlefield") and not c.tapped]  # {R} + {R}{R} paid
    check(s)


def test_ogre_declined_cast_leaves_the_spell_and_pumps_nothing(cards):
    from tests.wave110j_kit import ch

    s, ogre, bolt = _ogre(cards)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])  # the target card
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[])  # "or none"
    settle(s)
    assert now(s, bolt).zone.endswith(":graveyard") and ch(s, ogre).pt == (3, 3) and not s.state.rules.delayed
    check(s)


def test_ogre_two_mountains_cannot_pay_for_bolt_plus_rr(cards):
    """{R} for Bolt plus {R}{R} is three red mana: with two Mountains the payment is refused (601.2h) and Bolt stays in the graveyard."""
    s, ogre, bolt = _ogre(cards, mountains=2)
    for _ in range(2):
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][:1])
    d = s.state.rules.decision
    with pytest.raises(ActionError, match="Not enough mana to pay {R}{R}{R}"):
        act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2"])
    assert now(s, bolt).zone.endswith(":graveyard") and life(s, "p2") == 40
    check(s)


GOLEM = "Emblazoned Golem"


def _golem(cards, kicked, x, pool):
    from tests.wave110j_kit import mana

    s = build(cards, [GOLEM], [], forests=30, islands=30)
    spell = to_hand(s, GOLEM)
    mana(s, "p1", **pool)
    act(s, "p1", type="cast_spell", card_id=spell.id, kicker=kicked, x_value=x, sources=[])
    return s, spell


def test_golem_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(GOLEM)).level == "FULL"


def test_golem_x_paid_with_two_different_colors(cards):
    s, spell = _golem(cards, 1, 2, {"G": 2, "W": 1, "U": 1})  # {2} + X=2: G and W (or U) are X's, the rest pays {2}
    settle(s)
    assert now(s, spell).zone.endswith(":battlefield") and now(s, spell).counters.get("+1/+1") == 2
    check(s)


def test_golem_x_cannot_be_paid_with_one_color_twice(cards):
    with pytest.raises(ActionError):
        _golem(cards, 1, 2, {"G": 4})


def test_golem_x_cannot_be_paid_with_colorless_mana(cards):
    with pytest.raises(ActionError):
        _golem(cards, 1, 1, {"C": 3})


def test_golem_unkicked_is_unrestricted(cards):
    s, spell = _golem(cards, 0, 0, {"C": 2})
    settle(s)
    assert now(s, spell).zone.endswith(":battlefield") and not now(s, spell).counters.get("+1/+1")
    check(s)


GARTH = "Garth One-Eye"


def _garth(cards, extra=()):
    s = build(cards, [GARTH, "Grizzly Bears", *extra], ["Hill Giant"], forests=30, islands=30)
    garth = put_new(s, GARTH)
    giant = put_new(s, "Hill Giant", "p2")
    to_phase(s, "main1", turn=3)
    return s, garth, giant


def _activate(s, garth, name, answers=()):
    from tests.wave110j_kit import ability

    act(s, "p1", type="activate_ability", card_id=garth.id, ability=ability(s, garth, "{T}"))
    d = s.state.rules.decision
    assert d is not None and d.kind == "choose_one"
    return [o.id for o in d.options]


def test_garth_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(GARTH)).level == "FULL"


def test_garth_copies_terror_and_casts_it(cards):
    from tests.wave110j_kit import mana

    s, garth, giant = _garth(cards)
    mana(s, "p1", B=1, C=1)
    options = _activate(s, garth, "Terror")
    assert options == ["Disenchant", "Braingeyser", "Terror", "Shivan Dragon", "Regrowth", "Black Lotus"]
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Terror"])
    settle(s, answers=[[o.card_id for o in s.state.rules.decision.options][:1] if s.state.rules.decision and s.state.rules.decision.kind == "choose_cards" else None])
    assert now(s, giant).zone.endswith(":graveyard")  # Terror destroyed the nonblack, nonartifact Giant
    assert now(s, garth).choices.get("Names chosen") == "Terror"
    check(s)


def test_garth_declined_copy_still_uses_the_name_up_and_the_copy_ceases_to_exist(cards):
    s, garth, giant = _garth(cards)
    _activate(s, garth, "Terror")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Terror"])
    d = s.state.rules.decision
    assert d.kind == "choose_cards"  # "You may cast the copy"
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    assert now(s, giant).zone.endswith(":battlefield")
    assert not [c for c in s.state.cards.values() if c.is_token and c.name == "Terror"]  # (704.5e: a copy of a card that isn't a spell or on the battlefield)
    to_phase(s, "main1", turn=5)
    options = _activate(s, garth, "x")
    assert options == ["Disenchant", "Braingeyser", "Shivan Dragon", "Regrowth", "Black Lotus"]
    check(s)


def test_garth_that_left_and_returned_forgets(cards):
    s, garth, giant = _garth(cards)
    _activate(s, garth, "Terror")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["Terror"])
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    settle(s)
    act(s, "p1", type="move", card_ids=[garth.id], to={"zone": "hand"})
    act(s, "p1", type="move", card_ids=[garth.id], to={"player": "p1", "zone": "battlefield"})
    assert not now(s, garth).choices.get("Names chosen")  # 400.7: a new object remembers nothing
    check(s)
