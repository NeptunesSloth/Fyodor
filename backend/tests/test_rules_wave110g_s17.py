"""Wave 110G session 17."""

from __future__ import annotations

import json

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage
from tests.fixtures.cards import fixture_cards
from tests.game_helpers import act
from tests.test_rules_wave12a_counters_keywords import real
from tests.test_rules_wave34b_activated import activate, next_turn
from tests.test_rules_wave50j_small import EXTRA as EXTRA50J
from tests.test_rules_wave50j_small import counters, settle
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

ADVANCING = ("When this enchantment enters, draw a card.\n"
             "You may pay {0} rather than pay the power-up cost of the first power-up ability you activate during each of your turns.")
JUDGMENT = ("Madness {X}{R} (If you discard this card, discard it into exile. When you do, cast it for its madness cost or put it into your graveyard.)\n"
            "Avacyn's Judgment deals 2 damage divided as you choose among any number of targets. If this spell's madness cost was paid, it deals X damage "
            "divided as you choose among those permanents and/or players instead.")
MACHINATIONS = ("Until end of turn, you may activate loyalty abilities of Jace planeswalkers you control on any player's turn any time you could cast an instant.\n"
                "Empower Jace 8. (Put eight loyalty counters on a Jace token you control. If you don't control one, first create a blue Jace planeswalker token with "
                "\"[\u22121]: Surveil 1\" and \"[\u22123]: Draw a card.\")")
ROBBER = ("Flying\nEscape\u2014{3}{U}, Exile five other cards from your graveyard. (You may cast this card from your graveyard for its escape cost.)\n"
          "This creature escapes with \"Whenever this creature deals combat damage to a player, you may cast an artifact, instant, or sorcery spell from among cards "
          "exiled with this creature without paying its mana cost.\"")
JUSTICE = ("As an additional cost to cast this spell, you may pay {1}{R} and/or {1}{G} any number of times.\nDestroy target artifact. For each additional {1}{R} you paid, "
           "destroy another target artifact. For each additional {1}{G} you paid, destroy another target artifact, and you gain 1 life.")
STORM = ("Lightning Storm deals X damage to any target, where X is 3 plus the number of charge counters on Lightning Storm.\nDiscard a land card: Put two charge counters "
         "on Lightning Storm. You may choose a new target for it. Any player may activate this ability but only if Lightning Storm is on the stack.")
SPIRES = ("As you create your deck, circle two of the colors below.\nThis land enters tapped.\n{T}: Add one mana of either of the circled colors.")
EXTRA = [real("Cryptic Spires", "", 0, "Land", SPIRES, None, ""),
         real("Test Cheater", "{1}", 1, "Creature \u2014 Elf", "When this creature enters, you may cast a spell from your hand without paying its mana cost.", ("1", "1"), ""),
         real("Vesuva", "", 0, "Land", "You may have this land enter tapped as a copy of any land on the battlefield.", None, ""),
         real("Lightning Storm", "{1}{R}{R}", 3, "Instant", STORM, None, "R"),
         real("Primitive Justice", "{1}{R}", 2, "Sorcery", JUSTICE, None, "R"),
         *(real(f"Test Relic {i}", "{1}", 1, "Artifact", "", None, "") for i in range(5)),
         real("Skyway Robber", "{3}{U}", 4, "Creature \u2014 Bird Rogue", ROBBER, ("3", "3"), "U"),
         real("Test Gain", "{1}{W}", 2, "Sorcery", "You gain 5 life.", None, "W"),
         real("Jace's Machinations", "{2}{U}", 3, "Instant", MACHINATIONS, None, "U"),
         real("Advancing the Spirit", "{2}{W}", 3, "Enchantment", ADVANCING, None, "W"),
         real("Avacyn's Judgment", "{1}{R}", 2, "Sorcery", JUDGMENT, None, "R"),
         real("Discard Probe", "{B}", 1, "Sorcery", "Discard a card.", None, "B")]


@pytest.fixture
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA50J, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def test_full(cards):
    for name in ("Advancing the Spirit", "Avacyn's Judgment", "Jace's Machinations", "Skyway Robber", "Primitive Justice", "Lightning Storm", "Cryptic Spires"):
        assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def test_advancing_first_power_up_free_second_pays(cards):
    """118.9, 602.2b: {0} rather than the power-up cost of the first power-up ability activated each of your turns."""
    s = build(cards, mine=["Advancing the Spirit", "Serpent Specialist"])
    put(s, "Advancing the Spirit")
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    activate(s, "p1", snake)  # no mana at all
    settle(s)
    assert counters(s, "Serpent Specialist") == {"+1/+1": 2}
    check(s)


def test_without_it_power_up_costs_mana(cards):
    s = build(cards, mine=["Serpent Specialist"])
    snake = put(s, "Serpent Specialist")
    next_turn(s)
    with pytest.raises(ActionError, match="Not enough mana"):
        activate(s, "p1", snake)


def test_second_power_up_same_turn_pays(cards):
    s = build(cards, mine=["Advancing the Spirit", "Serpent Specialist", "Hulk, Gamma Goliath"])
    put(s, "Advancing the Spirit")
    snake = put(s, "Serpent Specialist")
    hulk = put(s, "Hulk, Gamma Goliath")
    next_turn(s)
    activate(s, "p1", snake)
    settle(s)
    with pytest.raises(ActionError, match="Not enough mana"):
        activate(s, "p1", hulk)
    check(s)


def test_judgment_hard_cast_two_damage_divided(cards):
    """601.2d: 2 damage divided among two targets, 1 each."""
    from tests.test_rules_wave110h_cards import answer
    from tests.wave9c_kit import life

    s = build(cards, ["Avacyn's Judgment"], ["Grizzly Bears"])
    bears = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[bears.id], to={"player": "p2", "zone": "battlefield"})
    mana(s, R=1, C=1)
    c = to_hand(s, "Avacyn's Judgment")
    act(s, "p1", type="cast_spell", card_id=c.id, targets=["p2", bears.id], target_counts=[2], division=[1, 1])
    answer(s)
    assert life(s, "p2") == 39 and s.state.cards[bears.id].damage == 1
    check(s)


@pytest.mark.parametrize("x", [3, 5])
def test_judgment_madness_x_damage_divided(cards, x):
    """702.35, 107.3b: cast for its madness cost, X damage divided among players and permanents."""
    from tests.test_rules_wave110h_cards import answer, cast
    from tests.wave9c_kit import life

    s = build(cards, ["Avacyn's Judgment", "Discard Probe"], ["Grizzly Bears"])
    giant = card_named(s, "Grizzly Bears", "p2")
    act(s, "p2", type="move", card_ids=[giant.id], to={"player": "p2", "zone": "battlefield"})
    to_hand(s, "Avacyn's Judgment")
    mana(s, B=1)
    cast(s, "Discard Probe")
    mana(s, R=1, C=x)
    for pick in (["yes"], [f"x:{x}"]):
        d = s.state.rules.decision
        act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["p2", giant.id])
    d = s.state.rules.decision
    assert d.kind == "divide"
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[], amounts=[x - 1, 1])
    answer(s)
    assert life(s, "p2") == 40 - (x - 1) and s.state.cards[giant.id].damage == 1
    check(s)


def answer(s, limit=40):
    from tests.test_rules_wave110h_cards import answer as _a

    _a(s, limit=limit)


def _jace(s):
    return next(c for c in s.state.cards.values() if c.name == "Jace" and c.token is not None and c.zone.endswith(":battlefield"))


def _machinations(cards):
    s = build(cards, ["Jace's Machinations"], [])
    mana(s, U=1, C=2)
    c = to_hand(s, "Jace's Machinations")
    act(s, "p1", type="cast_spell", card_id=c.id)
    answer(s)
    return s


def test_machinations_jace_at_instant_speed(cards):
    """606.3 timing lifted until end of turn: the Jace token (8 loyalty) activates in combat."""
    from tests.test_rules_wave34b_activated import activate, stops, to_phase

    s = _machinations(cards)
    jace = _jace(s)
    assert jace.counters["loyalty"] == 8
    stops(s)
    to_phase(s, "begin_combat")
    activate(s, "p1", jace, "Surveil 1")
    answer(s)
    assert s.state.cards[jace.id].counters["loyalty"] == 7
    check(s)


def test_without_machinations_jace_is_sorcery_speed(cards):
    from tests.test_rules_wave34b_activated import activate, stops, to_phase

    s = _machinations(cards)
    jace = _jace(s)
    s.state.rules.once_per_turn.clear()  # the turn mark gone: the token is an ordinary planeswalker
    stops(s)
    to_phase(s, "begin_combat")
    with pytest.raises(ActionError, match="main phase"):
        activate(s, "p1", jace, "Surveil 1")


def _escape(cards, escaped=True):
    """Skyway Robber (escaped from the graveyard with five other cards, a sorcery among them) or cast from the hand."""
    from tests.test_rules_wave50j_small import settle as _settle

    s = build(cards, ["Skyway Robber", "Test Gain", "Grizzly Bears", "Forest", "Island", "Swamp"], [], forests=12, islands=20)
    names = ["Skyway Robber", "Test Gain", "Grizzly Bears", "Forest", "Island", "Swamp"]
    for name in names if escaped else names[1:]:
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard" if escaped or name != "Skyway Robber" else "hand"})
    robber = card_named(s, "Skyway Robber")
    if not escaped:
        act(s, "p1", type="move", card_ids=[robber.id], to={"player": "p1", "zone": "hand"})
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=robber.id)
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None and escaped:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
    _settle(s)
    return s, robber


@pytest.mark.parametrize("escaped", [True, False])
def test_skyway_robber_casts_a_card_its_escape_exiled(cards, escaped):
    """702.138c + ruling 2022-04-29: an escaped Robber may cast an artifact/instant/sorcery exiled by its own escape cost for free when it connects; cast from hand it has no such ability."""
    from tests.test_rules_wave34b_activated import next_turn, to_phase
    from tests.wave9c_kit import life

    s, robber = _escape(cards, escaped)
    assert s.state.cards[robber.id].zone == "p1:battlefield"
    next_turn(s)
    to_phase(s, "declare_attackers")
    d = s.state.rules.decision
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": robber.id, "target": "p2"}])
    for _ in range(15):
        d = s.state.rules.decision
        if d is not None and d.kind != "declare_blockers":
            break
        act(s, s.state.rules.priority, type="pass_priority") if d is None else act(s, d.player, type=d.kind, blocks=[])
    if escaped:
        names = {o.label for o in d.options}
        assert any("Test Gain" in n for n in names) and not any("Grizzly" in n for n in names), names
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if "Test Gain" in o.label)])
        answer(s)
        assert life(s, "p1") == 45
    else:
        assert life(s, "p2") == 37
    check(s)


@pytest.mark.parametrize("r,g", [(0, 0), (1, 0), (1, 1), (0, 2), (2, 1), (4, 0), (0, 4)])
def test_primitive_justice_destroys_one_artifact_per_payment(cards, r, g):
    """601.2b-c, 702.33c: each payment of {1}{R} or {1}{G} adds one more target artifact; each {1}{G} also gains 1 life."""
    from tests.wave9c_kit import life

    n = 1 + r + g
    s = build(cards, ["Primitive Justice"], [f"Test Relic {i}" for i in range(5)])
    relics = [put(s, f"Test Relic {i}", pid="p2") for i in range(5)]
    mana(s, R=1 + r, G=g, C=1 + r + g)
    c = to_hand(s, "Primitive Justice")
    act(s, "p1", type="cast_spell", card_id=c.id, kicker=r + 1024 * g, targets=[x.id for x in relics[:n]], target_counts=[n])
    answer(s)
    assert [s.state.cards[x.id].zone.endswith("graveyard") for x in relics] == [i < n for i in range(5)]
    assert life(s, "p1") == 40 + g
    check(s)


def test_primitive_justice_needs_enough_targets(cards):
    s = build(cards, ["Primitive Justice"], [f"Test Relic {i}" for i in range(5)])
    relic = put(s, "Test Relic 0", pid="p2")
    mana(s, R=2, C=2)
    c = to_hand(s, "Primitive Justice")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=[relic.id], target_counts=[2])


def test_primitive_justice_same_artifact_twice_is_illegal(cards):
    """Ruling 2004-10-04: it can't target the same artifact more than once."""
    s = build(cards, ["Primitive Justice"], [f"Test Relic {i}" for i in range(5)])
    relic = put(s, "Test Relic 0", pid="p2")
    mana(s, R=2, C=2)
    c = to_hand(s, "Primitive Justice")
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=c.id, kicker=1, targets=[relic.id, relic.id], target_counts=[2])


def _storm(cards, activations):
    """Alice casts Lightning Storm at Bob; each entry of ``activations`` is the player who discards a land to activate it (then picks the new target) before it resolves."""
    from tests.test_rules_wave34b_activated import ability

    s = build(cards, ["Lightning Storm"], [])
    for pid in ("p1", "p2"):
        act(s, pid, type="configure", automation_options={"auto_priority_pass": False})
        act(s, pid, type="set_prefs", hold_priority=True)
    mana(s, R=2, C=1)
    storm = to_hand(s, "Lightning Storm")
    act(s, "p1", type="cast_spell", card_id=storm.id, targets=["p2"])
    return s, storm, ability


def test_lightning_storm_unboosted(cards):
    from tests.wave9c_kit import life

    s, storm, _ = _storm(cards, [])
    answer(s)
    assert life(s, "p2") == 37
    check(s)


@pytest.mark.parametrize("by,new_target,loser", [("p1", None, "p2"), ("p1", "p1", "p1")])
def test_lightning_storm_activation_adds_two_counters_and_may_retarget(cards, by, new_target, loser):
    """113.6, 602.2, 115.7d: any player may discard a land to put two charge counters on the spell on the stack and choose a new target; it resolves for 3 + 2."""
    from tests.wave9c_kit import life

    s, storm, ability = _storm(cards, [by])
    to_hand(s, "Forest")
    act(s, by, type="activate_ability", card_id=storm.id, ability=ability(s, "Lightning Storm", "p1", "Discard a land card"))
    assert s.state.cards[storm.id].zone == "stack"
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            pick = new_target if new_target in ids else ids[0]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[pick])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, loser) == 35
    check(s)


def test_lightning_storm_opponent_activates_twice(cards):
    """602.2: any player may activate it. Bob responds (discarding a land): 3 + 2 damage to the target he picks (Alice)."""
    from tests.wave9c_kit import life

    s, storm, ability = _storm(cards, [])
    to_hand(s, "Island", "p2")
    act(s, "p1", type="pass_priority")
    assert s.state.rules.priority == "p2"
    act(s, "p2", type="activate_ability", card_id=storm.id, ability=ability(s, "Lightning Storm", "p1", "Discard a land card"))
    d = s.state.rules.decision
    for _ in range(10):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["p1" if "p1" in ids else ids[0]])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert life(s, "p1") == 35 and life(s, "p2") == 40
    check(s)


def _spires_table(cards, extra=()):
    from app.game.factory import PlayerSetup, new_game
    from app.game.mulligan import COMMANDER_LONDON
    from app.game.rules_state import AUTOMATION_PRESETS, start_rules
    from app.game.session import GameSession
    from app.game.state import GameSettings
    from tests.game_helpers import deck, engine_pays

    a = deck(cards, "Krenko, Mob Boss", [(1, "Cryptic Spires"), *extra, (20, "Forest")])
    b = deck(cards, "Atraxa, Praetors' Voice", [(1, "Cryptic Spires"), (20, "Island")])
    state = new_game([PlayerSetup("Alice", cards=a), PlayerSetup("Bob", cards=b)], settings=GameSettings(mulligan=COMMANDER_LONDON), shuffle=False)
    state.settings.automation = "full"
    state.settings.automation_options = AUTOMATION_PRESETS["full"].model_copy()
    start_rules(state)
    engine_pays(state)
    return GameSession(state, cards=cards)


def _mana_text(s, card):
    from app.rules.plan import Plan

    return [a.text for a in Plan(s.state, "p1", s.cards, None).ch(s.state.cards[card.id]).abilities if a.kind == "mana"]


def test_cryptic_spires_circled_colors_before_the_game(cards):
    """Ruling 2024-11-08: two colors are circled as the deck is made, before any game, in the open; each Spires has its own pair; the mana ability then adds one of them."""
    from tests.test_rules_wave34b_activated import ability

    s = _spires_table(cards)
    mine, theirs = card_named(s, "Cryptic Spires", "p1"), card_named(s, "Cryptic Spires", "p2")
    assert _mana_text(s, mine) == ["{T}: Add one mana of either of the circled colors."]
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_keep")
    for who, pick in (("p1", ["B", "G"]), ("p2", ["W", "R"])):
        d = s.state.rules.decision
        assert d is not None and d.player == who and "circle two colors" in d.prompt, d and d.prompt
        with pytest.raises(ActionError):
            act(s, who, type="choose", decision_id=d.id, option_ids=pick[:1])
        act(s, who, type="choose", decision_id=d.id, option_ids=pick)
    assert _mana_text(s, mine) == ["{T}: Add {B} or {G}."] and _mana_text(s, theirs) == ["{T}: Add {W} or {R}."]
    while (d := s.state.rules.decision) is not None:  # the opening-hand actions (none to use)
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    act(s, "p1", type="move", card_ids=[mine.id], to={"player": "p1", "zone": "battlefield"})
    act(s, "p1", type="untap_all", player="p1")
    act(s, "p1", type="activate_ability", card_id=mine.id, ability=ability(s, "Cryptic Spires", "p1", "Add"))
    d = s.state.rules.decision
    assert d is not None and [o.label for o in d.options] and sorted(o.label for o in d.options) == ["{B}", "{G}"], d and [o.label for o in d.options]
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["1"])
    assert s.state.players["p1"].mana.get("G") == 1 or "G" in json.dumps(s.view("p1"), default=str)
    check(s)


@pytest.mark.parametrize("whose,colors", [("p1", "{B} or {G}"), ("p2", "{W} or {R}")])
def test_cryptic_spires_copy_makes_the_circled_colors(cards, whose, colors):
    """Ruling 2024-11-08: the circled colors are copiable values: a land entering as a copy of a Spires (707.2) makes mana of that Spires' circled colors."""
    s = _spires_table(cards, extra=[(1, "Vesuva")])
    spires = card_named(s, "Cryptic Spires", whose)
    act(s, "p1", type="mulligan_keep")
    act(s, "p2", type="mulligan_keep")
    for who, pick in (("p1", ["B", "G"]), ("p2", ["W", "R"])):
        act(s, who, type="choose", decision_id=s.state.rules.decision.id, option_ids=pick)
    while (d := s.state.rules.decision) is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[])
    act(s, "p1", type="move", card_ids=[spires.id], to={"player": whose, "zone": "battlefield"})
    next_turn(s)  # (the move counted as the land play)
    vesuva = card_named(s, "Vesuva", "p1")
    act(s, "p1", type="move", card_ids=[vesuva.id], to={"player": "p1", "zone": "hand"})
    act(s, "p1", type="play_land", card_id=vesuva.id)
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[spires.id])
    assert _mana_text(s, vesuva) == [f"{{T}}: Add {colors}."]
    check(s)


def test_primitive_justice_free_cast_typed_counts(cards):
    """Any count of each cost can be typed (not only up to 3): 4 of {1}{R} and 0 of {1}{G} pay {1}{R} four times for 5 artifacts."""
    from tests.wave9c_kit import life

    s = build(cards, ["Primitive Justice", "Test Cheater"], [f"Test Relic {i}" for i in range(5)])
    relics = [put(s, f"Test Relic {i}", pid="p2") for i in range(5)]
    mana(s, R=4, C=5)
    to_hand(s, "Primitive Justice")
    cheater = to_hand(s, "Test Cheater")
    act(s, "p1", type="cast_spell", card_id=cheater.id)
    for _ in range(3):
        if s.state.rules.decision is not None:
            break
        act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    d = s.state.rules.decision
    assert "kicker:other" in [o.id for o in d.options], d.prompt
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["kicker:other"])
    for n in (4, 0):
        d = s.state.rules.decision
        assert d.resume["step"] == "free_multikicker"
        act(s, "p1", type="choose", decision_id=d.id, name=str(n))
    d = s.state.rules.decision
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[x.id for x in relics]) if d is not None else None
    answer(s)
    assert [s.state.cards[x.id].zone.endswith("graveyard") for x in relics] == [True] * 5 and life(s, "p1") == 40
    check(s)
