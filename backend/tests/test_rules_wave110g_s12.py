"""Wave 110G session 12: Glamer Spinners, Skophos Maze-Warden, Equipoise.

* Glamer Spinners: 701.3b / 303.4 all Auras enchanting the target move to another permanent (not a target) with the same controller; an Aura that can't enchant it stays.
* Skophos Maze-Warden: 603.2 / 701.14 "another creature becomes the target of an ability of a land you control named Labyrinth of Skophos": may fight that creature.
* Stangg: 603.7 / 400.7 the delayed triggers made by its enter ability exile the token when Stangg leaves and sacrifice that same Stangg when the token leaves.
* Equipoise: 702.26 for lands, then artifacts, then creatures, as many of target player's as they control more than you phase out (counts retaken each time).
"""
from __future__ import annotations

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import build, card_named
from tests.wave110b_kit import cast, check, mana, put

LABY = "{T}: Add {C}.\n{4}, {T}: Remove target attacking or blocking creature from combat."
EXTRA = [
    real("Glamer Spinners", "{4}{W/U}", 5, "Creature — Faerie Wizard", "Flash\nFlying\nWhen this creature enters, attach all Auras enchanting target permanent to another permanent with the same controller.", ("2", "4"), "UW"),
    real("Skophos Maze-Warden", "{3}{R}", 4, "Creature — Minotaur Warrior", "{1}: This creature gets +1/-1 until end of turn.\nWhenever another creature becomes the target of an ability of a land you control named Labyrinth of Skophos, you may have this creature fight that creature. (Each deals damage equal to its power to the other.)", ("3", "4"), "R"),
    real("Labyrinth of Skophos", "", 0, "Land", LABY, None, ""),
    real("Labyrinth of Sophos", "", 0, "Land", LABY, None, ""),
    real("Equipoise", "{2}{W}", 3, "Enchantment", "At the beginning of your upkeep, for each land target player controls in excess of the number you control, choose a land that player controls, then the chosen permanents phase out. Repeat this process for artifacts and creatures. (While they're phased out, they're treated as though they don't exist. They phase in before that player untaps during their next untap step.)", None, "W"),
    real("Stangg", "{4}{R}{G}", 6, "Legendary Creature \u2014 Human Warrior", "When Stangg enters, create Stangg Twin, a legendary 3/4 red and green Human Warrior creature token. Exile that token when Stangg leaves the battlefield. Sacrifice Stangg when that token leaves the battlefield.", ("3", "4"), "GR"),
    real("Murder", "{1}{B}{B}", 3, "Instant", "Destroy target creature.", None, "B"),
    real("Unsummon", "{U}", 1, "Instant", "Return target creature to its owner's hand.", None, "U"),
    real("Squire", "{W}", 1, "Creature — Human", "", ("1", "1"), "W"),
    real("Bear Cub", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
    real("Land Aura", "{1}{G}", 2, "Enchantment — Aura", "Enchant land", None, "G"),
    real("Test Rock", "{1}", 1, "Artifact", "", None, ""),
    real("Dryad Arbor", "", 0, "Land Creature — Forest Dryad", "(This land isn't a spell, it's affected by summoning sickness, and it has \"{T}: Add {G}.\")", ("1", "1"), "G"),
]
NAMES = ["Glamer Spinners", "Skophos Maze-Warden", "Equipoise", "Stangg"]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def _attack_and_hold(s, creature):
    """Attack with ``creature`` and keep priority open in the declare attackers step (no auto pass for either player)."""
    s.state.rules.controlled_since[creature.id].turn = 0
    act(s, "p1", type="pass_priority")
    for p in ("p1", "p2"):
        act(s, p, type="configure", automation_options={"auto_priority_pass": False})
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": creature.id, "target": "p2"}])


def answer(s, ids=None, limit=60):
    """Settle the stack; each question gets ``ids`` (a list of option ids) if given, else the first option(s)."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids if ids is not None else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


@pytest.mark.parametrize("name", NAMES)
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def _glamer_setup(cards):
    s = build(cards, ["Glamer Spinners", "Pacifism", "Holy Strength", "Squire", "Bear Cub"], ["Island"])
    sq = put(s, "Squire")
    for n in ("Pacifism", "Holy Strength"):
        mana(s, "p1", W=1, C=2)
        cast(s, n, [sq.id])
    return s, sq


def _hand(s, name):
    from tests.wave9c_kit import to_hand

    return to_hand(s, name)


def _glamer(s, target, host):
    """Cast Glamer Spinners; its enter trigger targets ``target``, and ``host`` is picked on resolution. Returns the offered hosts' ids."""
    mana(s, "p1", W=1, C=4)
    act(s, "p1", type="cast_spell", card_id=_hand(s, "Glamer Spinners").id)
    offered: list[str] = []
    for _ in range(40):
        d = s.state.rules.decision
        if d is not None and "choose a target" in d.prompt:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[target.id])
        elif d is not None:
            offered = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[host.id])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    return offered


@pytest.mark.parametrize("dest, moved", [("creature", True), ("land", False)])
def test_glamer_spinners_moves_every_aura_that_can_enchant_the_chosen_permanent(cards, dest, moved):
    """Pacifism and Holy Strength (Enchant creature) go to the chosen creature; a land can't be enchanted by them, so they stay (701.3b)."""
    s, sq = _glamer_setup(cards)
    cub = put(s, "Bear Cub")
    host = cub if moved else put(s, "Forest")
    offered = _glamer(s, sq, host)
    assert host.id in offered and sq.id not in offered and {s.state.cards[i].zone for i in offered} == {"p1:battlefield"}
    here = {c.name: c.attached_to for c in s.state.cards.values() if c.name in ("Pacifism", "Holy Strength")}
    assert here == {n: (cub.id if moved else sq.id) for n in ("Pacifism", "Holy Strength")}
    check(s)


def test_glamer_spinners_only_considers_the_targets_controllers_permanents(cards):
    """Target an opponent's enchanted creature: only the opponent's other permanents are offered."""
    s = build(cards, ["Glamer Spinners", "Pacifism"], ["Bear Cub", "Squire", "Island"])
    cub, sq, _ = put(s, "Bear Cub", "p2"), put(s, "Squire", "p2"), put(s, "Island", "p2")
    put(s, "Forest")
    mana(s, "p1", W=1, C=2)
    cast(s, "Pacifism", [cub.id])
    offered = _glamer(s, cub, sq)
    assert offered and {s.state.cards[i].controller for i in offered} == {"p2"}
    assert card_named(s, "Pacifism").attached_to == sq.id
    check(s)


@pytest.mark.parametrize("land, owner, fights", [("Labyrinth of Skophos", "p1", True), ("Labyrinth of Sophos", "p1", False), ("Labyrinth of Skophos", "p2", False)])
def test_maze_warden_fights_only_after_a_named_labyrinth_you_control_targets(cards, land, owner, fights):
    s = build(cards, ["Skophos Maze-Warden", "Bear Cub", "Labyrinth of Skophos", "Labyrinth of Sophos"], ["Labyrinth of Skophos", "Island"])
    warden = put(s, "Skophos Maze-Warden")
    cub = put(s, "Bear Cub")
    lab = put(s, land, owner)
    _attack_and_hold(s, cub)
    assert s.state.turn.phase == "declare_attackers", s.state.turn.phase
    if owner == "p2":
        act(s, "p1", type="pass_priority")
    mana(s, owner, C=4)
    act(s, owner, type="activate_ability", card_id=lab.id, ability=1, targets=[cub.id], target_counts=[1])
    answer(s)
    assert (s.state.cards[cub.id].zone == "p1:graveyard") is fights  # Warden deals 3 to the 2/2 Cub
    assert (s.state.cards[warden.id].damage == 2) is fights
    check(s)


def test_maze_warden_may_decline(cards):
    s = build(cards, ["Skophos Maze-Warden", "Bear Cub", "Labyrinth of Skophos"], ["Island"])
    warden, cub, lab = put(s, "Skophos Maze-Warden"), put(s, "Bear Cub"), put(s, "Labyrinth of Skophos")
    _attack_and_hold(s, cub)
    mana(s, "p1", C=4)
    act(s, "p1", type="activate_ability", card_id=lab.id, ability=1, targets=[cub.id], target_counts=[1])
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            assert [o.id for o in d.options] == ["yes", "no"], d.options
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["no"])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[cub.id].zone == "p1:battlefield" and s.state.cards[cub.id].damage == 0 and s.state.cards[warden.id].damage == 0
    check(s)


def _upkeep(s, pick_target=None, picks=None):
    """On to Alice's turn-3 upkeep: the trigger's target (default p2), then each phase-out choice from ``picks`` (a list of card-id lists, or the first options)."""
    asked = []
    for _ in range(80):
        d = s.state.rules.decision
        if d is None and s.state.turn.number == 3 and s.state.turn.phase == "main1" and not s.state.zones.get("stack"):
            break
        if d is not None and d.kind == "choose_cards" and "phase out" in d.prompt:
            asked.append(d)
            ids = picks[len(asked) - 1] if picks else [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick_target or "p2"])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    return asked


def _phased(s, pid="p2"):
    return sorted(s.state.cards[c].name for c in s.state.zones.get(f"{pid}:phased", []))


def test_equipoise_phases_out_the_excess_of_each_kind(cards):
    """Lands: 3 vs 1, so 2 of the 3 (chosen) phase out; the lone artifact (1 vs 0) and both creatures (2 vs 0) go too, with no question (all of them)."""
    s = build(cards, ["Equipoise", "Forest"], ["Island", "Island", "Island", "Test Rock", "Squire", "Bear Cub"])
    put(s, "Equipoise")
    put(s, "Forest")
    for n in ("Test Rock", "Squire", "Bear Cub"):
        put(s, n, "p2")
    islands = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:3]
    for i in islands:
        act(s, "p2", type="move", card_ids=[i], to={"player": "p2", "zone": "battlefield"})
    asked = _upkeep(s, picks=[islands[:2]])
    assert len(asked) == 1 and asked[0].min_choices == 2 and len(asked[0].options) == 3
    assert _phased(s) == ["Bear Cub", "Island", "Island", "Squire", "Test Rock"]
    assert s.state.cards[islands[2]].zone == "p2:battlefield"
    check(s)


def test_equipoise_counts_again_after_a_land_creature_phased_out(cards):
    """Dryad Arbor is both: phasing it out as a land leaves no creature to exceed your zero (702.26b), so the creature step does nothing."""
    s = build(cards, ["Equipoise", "Forest"], ["Island", "Island", "Dryad Arbor"])
    put(s, "Equipoise")
    put(s, "Forest")
    arbor = put(s, "Dryad Arbor", "p2")
    isl = [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:2]
    for i in isl:
        act(s, "p2", type="move", card_ids=[i], to={"player": "p2", "zone": "battlefield"})
    asked = _upkeep(s, picks=[[arbor.id, isl[0]]])
    assert len(asked) == 1 and _phased(s) == ["Dryad Arbor", "Island"]
    check(s)


@pytest.mark.parametrize("mine, theirs", [(2, 2), (3, 2)])
def test_equipoise_does_nothing_without_an_excess(cards, mine, theirs):
    s = build(cards, ["Equipoise", "Forest"], ["Island", "Island"])
    put(s, "Equipoise")
    for _ in range(mine):
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.name == "Forest" and c.zone == "p1:library")], to={"player": "p1", "zone": "battlefield"})
    for i in [c.id for c in s.state.cards.values() if c.name == "Island" and c.owner == "p2"][:theirs]:
        act(s, "p2", type="move", card_ids=[i], to={"player": "p2", "zone": "battlefield"})
    assert _upkeep(s) == [] and _phased(s) == []


def _stangg_in_play(cards):
    s = build(cards, ["Stangg", "Murder", "Unsummon"], ["Murder", "Island"])
    mana(s, "p1", R=1, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=_hand(s, "Stangg").id)
    answer(s)
    return s


def _twin(s):
    return next((c for c in s.state.cards.values() if c.name == "Stangg Twin" and c.zone == "p1:battlefield"), None)


def test_stangg_makes_a_legendary_twin(cards):
    s = _stangg_in_play(cards)
    twin = _twin(s)
    assert twin is not None and card_named(s, "Stangg").zone == "p1:battlefield"
    from tests.wave110b_kit import ch

    c = ch(s, twin)
    assert (c.pt, sorted(c.colors), "Legendary" in c.supertypes) == ((3, 4), ["G", "R"], True)
    check(s)


@pytest.mark.parametrize("spell, victim", [("Murder", "Stangg"), ("Unsummon", "Stangg")])
def test_stangg_leaving_exiles_the_twin(cards, spell, victim):
    s = _stangg_in_play(cards)
    twin = _twin(s)
    mana(s, "p1", B=2, C=1, U=1)
    cast(s, spell, [card_named(s, victim).id])
    assert _twin(s) is None and (twin.id not in s.state.cards or s.state.cards[twin.id].zone not in ("p1:battlefield", "p1:graveyard"))
    check(s)


def test_stangg_is_sacrificed_when_its_twin_leaves(cards):
    s = _stangg_in_play(cards)
    mana(s, "p1", B=2, C=1)
    cast(s, "Murder", [_twin(s).id])
    assert card_named(s, "Stangg").zone == "p1:graveyard" and _twin(s) is None
    check(s)


def test_a_recast_stangg_is_not_sacrificed_for_the_old_twin(cards):
    """400.7: the first Stangg left (its twin was exiled); the new Stangg is a new object, and its own twin keeps it."""
    s = _stangg_in_play(cards)
    mana(s, "p1", U=1)
    cast(s, "Unsummon", [card_named(s, "Stangg").id])
    mana(s, "p1", R=1, G=1, C=4)
    act(s, "p1", type="cast_spell", card_id=_hand(s, "Stangg").id)
    answer(s)
    assert card_named(s, "Stangg").zone == "p1:battlefield" and _twin(s) is not None
    check(s)
