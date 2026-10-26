"""Wave 110J session 12, real Oracle text (tests/fixtures/wave110j_cards.json). Every scenario ends with replay + save/load.

* Paliano, the High City: 905.2 / 103.6 and the 2014-05-29 ruling: without a draft no color was chosen, so its mana ability taps for no mana (not even colorless).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.game_helpers import act
from tests.wave9c_kit import build, life
from tests.wave110j_kit import EXTRA, ability, card_db, cast_on, check, now, put_new, settle, to_phase  # noqa: F401

PALIANO = "Paliano, the High City"


def test_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(PALIANO)).level == "FULL"


def test_paliano_taps_for_no_mana(cards):
    s = build(cards, [PALIANO])
    p = put_new(s, PALIANO)
    act(s, "p1", type="activate_ability", card_id=p.id, ability=1)
    settle(s)
    assert now(s, p).tapped and s.state.players["p1"].mana == {} and not s.state.players["p1"].mana_units
    check(s)


TAKKLE = "Takklemaggot"


def _takkle_setup(cards, second_bear):
    s = build(cards, [TAKKLE, "Murder"], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    b1 = put_new(s, "Grizzly Bears", "p2")
    b2 = put_new(s, "Grizzly Bears", "p2") if second_bear else None
    t = cast_on(s, TAKKLE, b1)
    assert t.attached_to == b1.id if hasattr(t, "attached_to") else True
    cast_on(s, "Murder", b1)
    return s, t, b1, b2


def test_takklemaggot_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(TAKKLE)).level == "FULL"


def test_takklemaggot_returns_attached_to_the_creature_its_controller_picks(cards):
    s, t, b1, b2 = _takkle_setup(cards, True)
    settle(s, answers=[b2.id])
    t = now(s, t)
    assert t.zone == "p1:battlefield" and t.controller == "p1" and t.attached_to == b2.id
    check(s)


def test_takklemaggot_without_a_creature_returns_as_non_aura_that_pings(cards):
    s, t, b1, _ = _takkle_setup(cards, False)
    settle(s)
    t = now(s, t)
    assert t.zone == "p1:battlefield" and t.controller == "p1" and t.attached_to is None
    from tests.wave110j_kit import ch

    c = ch(s, t)
    assert "Aura" not in c.subtypes and not any(a.text.startswith("Enchant") for a in c.abilities)
    to_phase(s, "upkeep", turn=3)  # p2's turn-2 upkeep has passed: 1 damage each of its upkeeps, none on p1's
    settle(s)
    assert life(s, "p2") == 39 and life(s, "p1") == 40
    check(s)


CURSE = "Volrath's Curse"


def _curse_turn(cards):
    """p1 curses p2's Grizzly Bears; p2's turn 2, precombat main, bears are summoning-sick-free (put on the battlefield on turn 1)."""
    s = build(cards, [CURSE], ["Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    bears = put_new(s, "Grizzly Bears", "p2")
    put_new(s, "Grizzly Bears", "p2")
    cast_on(s, CURSE, bears)
    act(s, "p2", type="set_stops", own=["declare_attackers"])
    to_phase(s, "main1", turn=2)
    return s, bears


def _attack(s, bears):
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p1"}])


def test_volrath_curse_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(CURSE)).level == "FULL"


def test_volrath_curse_stops_attacks_and_activations(cards):
    s, bears = _curse_turn(cards)
    act(s, "p2", type="pass_priority")
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
        if s.state.turn.phase not in ("main1", "beginning_of_combat", "declare_attackers"):
            break
    import pytest

    from app.game.errors import ActionError

    with pytest.raises(ActionError):
        _attack(s, bears)
    check(s)


def test_volrath_curse_is_ignored_by_sacrificing_a_permanent(cards):
    s, bears = _curse_turn(cards)
    forest = next(c for c in s.state.cards.values() if c.name == "Grizzly Bears" and c.owner == "p2" and c.id != bears.id and c.zone.endswith(":battlefield"))  # (any permanent will do)
    from tests.wave110j_kit import ability

    act(s, "p2", type="activate_ability", card_id=bears.id, ability=ability(s, bears, "Sacrifice a permanent"))
    settle(s, answers=[forest.id])
    assert now(s, forest).zone.endswith(":graveyard")
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    _attack(s, bears)
    settle(s)
    assert now(s, bears).attacking is not None
    check(s)


EQ = "Equinox"


def _equinox(cards, spell, own_target):
    """p1 enchants its Forest with Equinox, casts ``spell`` (Stone Rain at its own or p2's Forest, or Armageddon) and holds priority to use Equinox on it."""
    from tests.wave9c_kit import card_named, mana
    from tests.wave110j_kit import hand_new

    s = build(cards, [EQ, spell], [], forests=30, islands=30)
    mine, theirs = put_new(s, "Forest"), put_new(s, "Island", "p2")
    cast_on(s, EQ, mine)
    assert now(s, card_named(s, EQ)).attached_to == mine.id
    c = hand_new(s, spell)
    act(s, "p1", type="set_stops", hold_priority=True, smart_pass=False)
    mana(s, "p1", R=3, C=3, W=2)
    target = {} if spell == "Armageddon" else {"targets": [mine.id if own_target else theirs.id]}
    act(s, "p1", type="cast_spell", card_id=c.id, **target)
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=ability(s, mine, "{T}: Counter"), targets=[c.id])
    settle(s)
    return s, c, mine, theirs


def test_equinox_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(EQ)).level == "FULL"


@pytest.mark.parametrize("spell,own,countered", [("Stone Rain", True, True), ("Stone Rain", False, False), ("Armageddon", True, True)])
def test_equinox_counters_only_a_spell_that_would_destroy_a_land_you_control(cards, spell, own, countered):
    s, c, mine, theirs = _equinox(cards, spell, own)
    assert now(s, c).zone == "p1:graveyard"
    assert now(s, mine).zone.endswith(":battlefield") and now(s, theirs).zone.endswith(":battlefield") == countered  # the spell resolved (and destroyed theirs) unless Equinox countered it
    check(s)


def test_volrath_curse_two_curses_each_need_their_own_sacrifice(cards):
    """113.10 / 611.3a: each Curse is its own effect; sacrificing for one ignores only that Curse, the other still stops attacks."""
    s = build(cards, [CURSE, CURSE], ["Grizzly Bears", "Grizzly Bears", "Grizzly Bears"], forests=30, islands=30)
    bears = put_new(s, "Grizzly Bears", "p2")
    fodder = [put_new(s, "Grizzly Bears", "p2") for _ in range(2)]
    cast_on(s, CURSE, bears)
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import hand_new

    second = hand_new(s, CURSE)  # (cast_on takes the first copy by name: that is the one already on the battlefield)
    mana(s, "p1", U=1, C=1)
    act(s, "p1", type="cast_spell", card_id=second.id, targets=[bears.id])
    settle(s)
    act(s, "p2", type="set_stops", own=["declare_attackers"])
    to_phase(s, "main1", turn=2)
    ignores = [a.index for a in ch_abilities(s, bears) if a.text.startswith("Sacrifice a permanent: Ignore")]
    assert len(ignores) == 2
    act(s, "p2", type="activate_ability", card_id=bears.id, ability=ignores[0])
    settle(s, answers=[fodder[0].id])
    while s.state.rules.decision is None or s.state.rules.decision.kind != "declare_attackers":
        act(s, s.state.rules.priority, type="pass_priority")
    with pytest.raises(ActionError):
        _attack(s, bears)  # one Curse paid, the other still restricts
    check(s)


def ch_abilities(s, c):
    from tests.wave110j_kit import ch

    return ch(s, c).abilities


def test_equinox_unclear_spell_goes_to_manual_resolution(cards):
    """Equinox can't tell whether a modal spell would destroy a land: no player rules on it; the ability is resolved by hand."""
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import hand_new

    s = build(cards, [EQ, "Abrade"], ["Grizzly Bears"], forests=30, islands=30)
    mine, bears = put_new(s, "Forest"), put_new(s, "Grizzly Bears", "p2")
    cast_on(s, EQ, mine)
    c = hand_new(s, "Abrade")
    act(s, "p1", type="set_stops", hold_priority=True, smart_pass=False)
    mana(s, "p1", R=1, C=1)
    act(s, "p1", type="cast_spell", card_id=c.id, modes=[0], targets=[bears.id])
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=ability(s, mine, "{T}: Counter"), targets=[c.id])
    for _ in range(10):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    assert d is not None and d.kind == "manual_resolution" and "Equinox" in d.prompt
    settle(s)
    check(s)


BEAST = "Guardian Beast"


def _beast(cards, tapped):
    """p1 has Guardian Beast (tapped or not) and a Sol Ring; p2 has a Sol Ring, Steal Artifact and Shifting Loyalties and is in its precombat main."""
    s = build(cards, [BEAST, "Sol Ring"], ["Sol Ring", "Steal Artifact", "Shifting Loyalties"], forests=30, islands=30)
    beast, ring = put_new(s, BEAST), put_new(s, "Sol Ring")
    mine = put_new(s, "Sol Ring", "p2")
    from tests.wave110j_kit import hand_new

    for name in ("Steal Artifact", "Shifting Loyalties"):
        hand_new(s, name, "p2")  # (before turn 2's draw empties the small library)
    if tapped:
        act(s, "p1", type="tap", card_ids=[beast.id], tapped=True)
    to_phase(s, "main1", turn=2)
    return s, ring, mine


def test_guardian_beast_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(BEAST)).level == "FULL"


@pytest.mark.parametrize("tapped", [False, True])
def test_guardian_beast_untapped_artifacts_are_indestructible_and_cant_be_enchanted(cards, tapped):
    """101.2 / 303.4: while untapped no Aura spell can target its controller's noncreature artifact; tapped, nothing is protected."""
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import ch

    s, ring, _ = _beast(cards, tapped)
    assert ("indestructible" in ch(s, now(s, ring)).keywords) == (not tapped)
    aura = next(c for c in s.state.cards.values() if c.name == "Steal Artifact")
    mana(s, "p2", U=2, C=2)
    if tapped:
        act(s, "p2", type="cast_spell", card_id=aura.id, targets=[ring.id])
        settle(s)
        assert now(s, ring).controller == "p2"
    else:
        with pytest.raises(ActionError):
            act(s, "p2", type="cast_spell", card_id=aura.id, targets=[ring.id])
    check(s)


@pytest.mark.parametrize("tapped", [False, True])
def test_guardian_beast_blocks_exchange_of_control(cards, tapped):
    """101.2 + 701.12a: other players can't gain control of the protected artifact, so the exchange does nothing; tapped, it happens."""
    from tests.wave9c_kit import mana

    s, ring, mine = _beast(cards, tapped)
    spell = next(c for c in s.state.cards.values() if c.name == "Shifting Loyalties")
    mana(s, "p2", U=1, C=5)
    act(s, "p2", type="cast_spell", card_id=spell.id, targets=[ring.id, mine.id], target_counts=[2])
    settle(s)
    assert (now(s, ring).controller, now(s, mine).controller) == (("p2", "p1") if tapped else ("p1", "p2"))
    check(s)


KIT = "Spy Kit"


def test_spy_kit_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(KIT)).level == "FULL"


def test_spy_kit_gives_the_equipped_creature_every_nonlegendary_creature_name(cards):
    """201.2 / 201.4: Pithing Needle naming "Grizzly Bears" stops the equipped Sorcerer's tap ability (it has that name too), not an unequipped one."""
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import activate, hand_new

    s = build(cards, [KIT, "Pithing Needle", "Prodigal Sorcerer"], [], forests=30, islands=30)
    sorc, kit = put_new(s, "Prodigal Sorcerer"), put_new(s, KIT)
    mana(s, "p1", C=2)
    activate(s, kit, "Equip {2}", targets=[sorc.id])
    assert now(s, kit).attached_to == sorc.id
    needle = hand_new(s, "Pithing Needle")
    mana(s, "p1", C=1)
    act(s, "p1", type="cast_spell", card_id=needle.id)
    while s.state.rules.decision is None:
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, name="Grizzly Bears")
    settle(s)
    to_phase(s, "main1", turn=3)  # (no summoning sickness)
    with pytest.raises(ActionError, match="can't be activated"):
        act(s, "p1", type="activate_ability", card_id=sorc.id, ability=ability(s, sorc, "{T}"), targets=["p2"])
    act(s, "p1", type="move", card_ids=[kit.id], to={"zone": "graveyard"})  # unequipped: the Sorcerer has only its own name
    act(s, "p1", type="activate_ability", card_id=sorc.id, ability=ability(s, sorc, "{T}"), targets=["p2"])
    settle(s)
    check(s)


BRAWL = "Bludgeon Brawl"


def test_bludgeon_brawl_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(BRAWL)).level == "FULL"


def test_bludgeon_brawl_makes_each_artifact_an_equipment_with_its_own_mana_value(cards):
    """205.1b, 613.1d/f: a noncreature artifact is an Equipment with equip {X} and +X/+0, X its own mana value (Thran Dynamo 4, Sol Ring 1); a creature isn't."""
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import activate, ch

    s = build(cards, [BRAWL, "Thran Dynamo", "Sol Ring", "Grizzly Bears"], [], forests=30, islands=30)
    brawl, dyn, ring, bears = (put_new(s, n) for n in (BRAWL, "Thran Dynamo", "Sol Ring", "Grizzly Bears"))
    assert "Equipment" in ch(s, now(s, dyn)).subtypes and "Equipment" in ch(s, now(s, ring)).subtypes
    mana(s, "p1", C=4)
    activate(s, dyn, "Equip {4}", targets=[bears.id])
    assert now(s, dyn).attached_to == bears.id and ch(s, now(s, bears)).pt == (6, 2)
    mana(s, "p1", C=1)
    activate(s, ring, "Equip {1}", targets=[bears.id])
    assert ch(s, now(s, bears)).pt == (7, 2)
    check(s)
    act(s, "p1", type="move", card_ids=[brawl.id], to={"zone": "graveyard"})  # it leaves: no more Equipment, the +X/+0 ends
    assert "Equipment" not in ch(s, now(s, dyn)).subtypes and ch(s, now(s, bears)).pt == (2, 2)


VS = "Volrath's Shapeshifter"


def test_volrath_shapeshifter_full(cards):
    from app.rules import coverage

    assert coverage.of_card_data(cards.resolve(VS)).level == "FULL"


def test_volrath_shapeshifter_takes_the_full_text_of_the_top_creature_card(cards):
    """612.6 + 613.1c: name, mana cost, color, types, P/T and abilities of the top creature card (and {2}: Discard a card); a noncreature on top, or none, leaves it as printed."""
    from tests.wave9c_kit import mana
    from tests.wave110j_kit import activate, ch, grave_new, hand_new

    s = build(cards, [VS, "Prodigal Sorcerer", "Sol Ring", "Grizzly Bears"], [], forests=30, islands=30)
    vs = put_new(s, VS)
    assert (ch(s, now(s, vs)).name, ch(s, now(s, vs)).pt) == (VS, (0, 1))
    grave_new(s, "Prodigal Sorcerer")
    now_ch = ch(s, now(s, vs))
    assert (now_ch.name, now_ch.pt, now_ch.mana_cost) == ("Prodigal Sorcerer", (1, 1), "{2}{U}") and {"Human", "Wizard"} <= set(now_ch.subtypes)
    assert any(a.text.startswith("{T}: ") for a in now_ch.abilities) and any(a.text == "{2}: Discard a card." for a in now_ch.abilities)
    hand_new(s, "Grizzly Bears")  # "{2}: Discard a card." puts the card it discards on top, so the Shapeshifter follows it
    mana(s, "p1", C=2)
    activate(s, vs, "{2}: Discard a card.")
    assert (ch(s, now(s, vs)).name, ch(s, now(s, vs)).pt) == ("Grizzly Bears", (2, 2))
    grave_new(s, "Sol Ring")  # a noncreature card is now on top: as printed
    assert ch(s, now(s, vs)).name == VS
    check(s)
