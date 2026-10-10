"""Wave 28A: playing a card as an effect resolves (CR 2026-09-25). Real Oracle text; every scenario checks the replay and a save and a load
(the pauses mid-choice too).

* 608.2g: an effect that allows casting a spell during resolution follows 601.2a-i with no priority; timing is ignored. A land is not cast:
  playing one as an effect is 305.1's special action done by the effect, so it never uses the stack.
* 305.2a / 305.2b: it counts against the lands the player can play this turn (lands played during resolutions count), and with none left the
  instruction is ignored. 305.3: only on the player's own turn.
* 712.12: a modal double-faced card played as a land: the player chooses which face (a land face) before it enters, and it enters with that
  face up. 709.3: a split card is cast as one half.
* Nothing is kept: a card not played now can't be played this way later.
"""

from __future__ import annotations

import json

import pytest

from app.rules import coverage, scripts
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_conditionals import to_turn
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.wave9c_kit import build, card_named, mana, put, reloaded, to_hand, zone_of


def _face(name, mc, tl, text, p=None, t=None):
    return {"object": "card_face", "name": name, "mana_cost": mc, "type_line": tl, "oracle_text": text, "power": p, "toughness": t}


REAL = [
    card("Horde of Notions", set_code="t28a", number="A1", mana_cost="{W}{U}{B}{R}{G}", cmc=5.0, type_line="Legendary Creature — Elemental",
         colors=["W", "U", "B", "R", "G"], color_identity=["W", "U", "B", "R", "G"], power="5", toughness="5",
         keywords=["Vigilance", "Trample", "Haste"],
         oracle_text="Vigilance, trample, haste\n{W}{U}{B}{R}{G}: You may play target Elemental card from your graveyard without paying its mana cost."),
    card("Mulldrifter", set_code="t28a", number="A2", mana_cost="{4}{U}", cmc=5.0, type_line="Creature — Elemental", colors=["U"],
         color_identity=["U"], power="2", toughness="2", keywords=["Flying", "Evoke"],
         oracle_text="Flying\nWhen this creature enters, draw two cards.\nEvoke {2}{U} (You may cast this spell for its evoke cost. If you do, "
                     "it's sacrificed when it enters.)"),
    card("Tangled Florahedron // Tangled Vale", set_code="t28a", number="A3", layout="modal_dfc", mana_cost="{1}{G}", cmc=2.0,
         type_line="Creature — Elemental // Land", colors=["G"], color_identity=["G"],
         card_faces=[_face("Tangled Florahedron", "{1}{G}", "Creature — Elemental", "{T}: Add {G}.", "1", "1"),
                     _face("Tangled Vale", "", "Land", "This land enters tapped.\n{T}: Add {G}.")]),
    card("Valakut Awakening // Valakut Stoneforge", set_code="t28a", number="A4", layout="modal_dfc", mana_cost="{2}{R}", cmc=3.0,
         type_line="Instant // Land", colors=["R"], color_identity=["R"],
         card_faces=[_face("Valakut Awakening", "{2}{R}", "Instant",
                           "Put any number of cards from your hand on the bottom of your library, then draw that many cards plus one."),
                     _face("Valakut Stoneforge", "", "Land", "This land enters tapped.\n{T}: Add {R}.")]),
    card("Djinn of Wishes", set_code="t28a", number="A5", mana_cost="{3}{U}{U}", cmc=5.0, type_line="Creature — Djinn", colors=["U"],
         color_identity=["U"], power="4", toughness="4", keywords=["Flying"],
         oracle_text="Flying\nThis creature enters with three wish counters on it.\n{2}{U}{U}, Remove a wish counter from this creature: Reveal "
                     "the top card of your library. You may play that card without paying its mana cost. If you don't, exile it."),
    card("Gix, Yawgmoth Praetor", set_code="t28a", number="A7", mana_cost="{1}{B}{B}", cmc=3.0, type_line="Legendary Creature — Phyrexian Praetor",
         colors=["B"], color_identity=["B"], power="3", toughness="3",
         oracle_text="Whenever a creature deals combat damage to one of your opponents, its controller may pay 1 life. If they do, they draw a card.\n"
         "{4}{B}{B}{B}, Discard X cards: Exile the top X cards of target opponent's library. You may play lands and cast spells from among cards "
         "exiled this way without paying their mana costs."),
]
OURS = [c["name"] for c in REAL]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def to_gy(s, name):
    c = card_named(s, name)
    act(s, "p1", type="move", card_ids=[c.id], to={"zone": "graveyard"})
    return c


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def pick(s, option):
    d = decision(s)
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[option])
    pass_until_stack_empty(s)


def option_ids(s):
    return [o.id for o in decision(s).options]


def horde_ready(s, *grave):
    horde = put(s, "Horde of Notions")
    s.state.rules.controlled_since[horde.id].turn = 0
    ids = [to_gy(s, n).id for n in grave]
    return horde, ids


def activate(s, horde, target):
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="activate_ability", card_id=horde.id, ability=1, targets=[target])
    pass_until_stack_empty(s)  # (both players pass: the ability resolves, a choice comes up)


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_the_wording_is_read():
    parsed = scripts.parse_effects("You may play target Elemental card from your graveyard without paying its mana cost.")
    assert parsed is not None
    e = parsed[0][0]
    assert e["do"] == "free_cast" and e["play"] is True and e["zone"] == "target" and "paid" not in e
    paid = scripts.parse_effects("You may play target Elemental card from your graveyard.")
    assert paid is not None and paid[0][0]["play"] is True and paid[0][0]["paid"] is True
    # a duration is the permission's (611.2a), never this
    timed = scripts.parse_effects("You may play target Elemental card from your graveyard this turn.")
    assert timed is not None and timed[0][0]["do"] == "grant_play"


def test_horde_of_notions_is_full(cards):
    assert coverage.of_card_data(cards.resolve("Horde of Notions")).level == "FULL"


def test_plays_a_creature_card_without_paying(cards):
    s = build(cards, OURS)
    horde, (drifter,) = horde_ready(s, "Mulldrifter")
    activate(s, horde, drifter)
    d = decision(s)
    assert d.options and drifter in option_ids(s)
    before = len(s.state.zones["p1:hand"])
    pick(s, drifter)
    assert zone_of(s, "Mulldrifter") == "p1:battlefield"
    assert len(s.state.zones["p1:hand"]) == before + 2  # its enters trigger drew two
    assert s.state.players["p1"].mana == {}
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 0  # (a spell, not a land play)
    assert s.state.rules.free_casts == [] and s.state.rules.free_cast_then is None
    check(s)


def test_a_creature_can_be_declined_and_stays_in_the_graveyard(cards):
    s = build(cards, OURS)
    horde, (drifter,) = horde_ready(s, "Mulldrifter")
    activate(s, horde, drifter)
    pick(s, "none") if "none" in option_ids(s) else act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    pass_until_stack_empty(s)
    assert zone_of(s, "Mulldrifter") == "p1:graveyard"
    assert s.state.rules.permissions == []  # (nothing is kept: no later "may play")
    check(s)


def test_a_modal_double_faced_card_is_played_as_its_land_face(cards):
    s = build(cards, OURS)
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    activate(s, horde, florahedron)
    labels = {o.id: o.label for o in decision(s).options}
    assert len(labels) == 2  # 712.12: the player chooses the face: the creature spell, or the land
    land = next(i for i, label in labels.items() if "Tangled Vale" in label)
    pick(s, land)
    c = s.state.cards[florahedron]
    assert c.zone == "p1:battlefield" and c.face == 1  # it enters with the land face up
    assert c.tapped  # (this land enters tapped)
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1  # 305.2a: it was a land play
    check(s)


def test_a_land_played_by_an_effect_triggers_landfall(cards):
    s = build(cards, [*OURS, "Courser of Kruphix"])
    put(s, "Courser of Kruphix")
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    life = s.state.players["p1"].life
    activate(s, horde, florahedron)
    land = next(o.id for o in decision(s).options if "Tangled Vale" in o.label)
    pick(s, land)
    assert s.state.players["p1"].life == life + 1  # "Landfall — Whenever a land you control enters, you gain 1 life."
    check(s)


def test_the_other_wordings_are_read():
    one = scripts.parse_effects("Exile the top three cards of your library. You may play one of those cards without paying its mana cost.")
    assert one is not None and one[0][1]["do"] == "free_cast" and one[0][1]["play"] is True and one[0][1]["n"] == 1
    bare = scripts.parse_effects("Exile the top card of your library. You may play that card.")
    assert bare is not None and bare[0][1]["play"] is True and bare[0][1]["paid"] is True  # (as it resolves; its mana cost is paid)
    free = scripts.parse_effects("Exile the top card of your library. You may play that card without paying its mana cost.")
    assert free is not None and free[0][1]["play"] is True and "paid" not in free[0][1]
    # several cards at once, and a bare "you may play those cards", stay manual
    assert scripts.parse_effects("Exile the top two cards of your library. You may play those cards without paying their mana costs.") is None


def test_a_modal_double_faced_card_is_cast_as_its_front_face(cards):
    s = build(cards, OURS)
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    activate(s, horde, florahedron)
    spell = next(o.id for o in decision(s).options if "Tangled Vale" not in o.label)
    pick(s, spell)
    c = s.state.cards[florahedron]
    assert c.zone == "p1:battlefield" and not c.face
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 0
    check(s)


def test_no_land_play_left_offers_only_the_spell_face(cards):
    s = build(cards, OURS)
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)  # the turn's land play is used (305.2a)
    activate(s, horde, florahedron)
    labels = [o.label for o in decision(s).options]
    assert len(labels) == 1 and "Tangled Vale" not in labels[0]  # 305.2b: the land can't be played
    check(s)


def test_a_land_alone_with_no_land_play_does_nothing(cards):
    s = build(cards, OURS + ["Forest"])
    horde, (stoneforge,) = horde_ready(s, "Valakut Awakening // Valakut Stoneforge")
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)
    # (the card is not an Elemental: Horde can't target it, so this checks the ability's own target restriction)
    mana(s, W=1, U=1, B=1, R=1, G=1)
    with pytest.raises(Exception):  # noqa: B017  (an illegal target)
        act(s, "p1", type="activate_ability", card_id=horde.id, ability=1, targets=[stoneforge])


def test_the_land_is_not_playable_on_an_opponents_turn(cards):
    s = build(cards, OURS, theirs=["Lightning Bolt"])
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    to_turn(s, 2)  # Bob's first main phase
    assert s.state.turn.active_player == "p2"
    to_hand(s, "Lightning Bolt", "p2")
    mana(s, "p2", R=1)
    act(s, "p1", type="set_prefs", response="on")
    act(s, "p2", type="set_prefs", hold_priority=True)
    act(s, "p2", type="cast_spell", card_id=card_named(s, "Lightning Bolt", "p2").id, targets=["p2"])
    act(s, "p2", type="pass_priority")
    mana(s, W=1, U=1, B=1, R=1, G=1)  # (Alice responds: priority is hers)
    act(s, "p1", type="set_prefs", hold_priority=True)
    act(s, "p1", type="activate_ability", card_id=horde.id, ability=1, targets=[florahedron])
    pass_until_stack_empty(s)
    labels = [o.label for o in decision(s).options]
    assert len(labels) == 1 and "Tangled Vale" not in labels[0]  # 305.3
    check(s)


def test_pausing_on_the_choice_survives_a_save_and_load(cards):
    s = build(cards, OURS)
    horde, (florahedron,) = horde_ready(s, "Tangled Florahedron // Tangled Vale")
    activate(s, horde, florahedron)
    other = reloaded(s)
    assert other.state.rules.decision is not None and other.state.rules.decision.id == decision(s).id
    land = next(o.id for o in decision(other).options if "Tangled Vale" in o.label)
    act(other, "p1", type="choose", decision_id=decision(other).id, option_ids=[land])
    pass_until_stack_empty(other)
    assert other.state.cards[florahedron].zone == "p1:battlefield" and other.state.cards[florahedron].face == 1
    replay_matches(other)
    assert reloaded(other).state.model_dump(mode="json") == other.state.model_dump(mode="json")


def test_the_targets_card_must_still_be_there(cards):
    s = build(cards, OURS)
    horde, (drifter,) = horde_ready(s, "Mulldrifter")
    act(s, "p1", type="set_prefs", hold_priority=True)
    mana(s, W=1, U=1, B=1, R=1, G=1)
    act(s, "p1", type="activate_ability", card_id=horde.id, ability=1, targets=[drifter])
    act(s, "p1", type="move", card_ids=[drifter], to={"zone": "exile"})  # (in response)
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None, (s.state.rules.decision.options, s.state.cards[drifter].zone)  # 608.2b
    assert zone_of(s, "Mulldrifter") == "p1:exile"
    check(s)


def hidden_from_bob(s, secret):
    for session in (s, reloaded(s)):
        assert secret not in json.dumps(session.view("p2"), default=str)


def test_djinn_of_wishes_plays_the_revealed_land_with_a_land_play(cards):
    s = build(cards, OURS)
    djinn = put(s, "Djinn of Wishes")
    s.state.rules.controlled_since[djinn.id].turn = 0
    act(s, "p1", type="counter", card_ids=[djinn.id], kind="wish", delta=3)
    top = card_named(s, "Valakut Awakening // Valakut Stoneforge")
    act(s, "p1", type="move", card_ids=[top.id], to={"zone": "library"}, position="top")
    mana(s, U=2, C=2)
    act(s, "p1", type="activate_ability", card_id=djinn.id, ability=2)
    pass_until_stack_empty(s)
    d = decision(s)
    labels = {o.id: o.label for o in d.options}
    land = next(i for i, label in labels.items() if "Stoneforge" in label)
    pick(s, land)
    assert s.state.cards[top.id].zone == "p1:battlefield" and s.state.cards[top.id].face == 1
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1
    check(s)


def djinn_with_top(s, name):
    djinn = put(s, "Djinn of Wishes")
    s.state.rules.controlled_since[djinn.id].turn = 0
    act(s, "p1", type="counter", card_ids=[djinn.id], kind="wish", delta=3)
    top = card_named(s, name)
    act(s, "p1", type="move", card_ids=[top.id], to={"zone": "library"}, position="top")
    mana(s, U=2, C=2)
    act(s, "p1", type="activate_ability", card_id=djinn.id, ability=2)
    pass_until_stack_empty(s)
    return top


def test_declining_the_revealed_card_exiles_it(cards):
    s = build(cards, OURS)
    top = djinn_with_top(s, "Mulldrifter")
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])  # "You may": no
    pass_until_stack_empty(s)
    assert s.state.cards[top.id].zone == "p1:exile"  # "If you don't, exile it."
    check(s)


def test_the_revealed_land_is_exiled_when_no_land_play_is_left(cards):
    s = build(cards, OURS)
    forest = next(c for c in s.state.cards.values() if c.name == "Forest" and c.owner == "p1" and c.zone == "p1:library")
    act(s, "p1", type="move", card_ids=[forest.id], to={"zone": "hand"})
    act(s, "p1", type="play_land", card_id=forest.id)  # 305.2b: the land play of the turn is used
    top = djinn_with_top(s, "Valakut Awakening // Valakut Stoneforge")
    assert [o.label for o in decision(s).options] == ["Valakut Awakening"]  # (only its spell face; asked all the same: nothing is leaked)
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[])
    pass_until_stack_empty(s)
    assert s.state.cards[top.id].zone == "p1:exile"
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 1
    check(s)


def test_the_revealed_spell_face_of_a_modal_card_is_cast(cards):
    s = build(cards, OURS)
    top = djinn_with_top(s, "Valakut Awakening // Valakut Stoneforge")
    spell = next(o.id for o in decision(s).options if "Stoneforge" not in o.label)
    pick(s, spell)
    assert s.state.cards[top.id].zone == "p1:graveyard"  # an instant: cast and resolved
    check(s)


def test_a_split_card_is_cast_as_the_half_chosen(cards):
    s = build(cards, [*OURS, "Fire // Ice"])
    top = djinn_with_top(s, "Fire // Ice")
    assert sorted(o.label for o in decision(s).options) == ["Fire", "Ice"]  # 709.3: one half is cast
    ice = next(o.id for o in decision(s).options if o.label == "Ice")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[ice])
    for _ in range(6):  # Ice's target, then it resolves: tap it, draw a card
        d = s.state.rules.decision
        if d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            break
    assert s.state.cards[top.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand + 1
    check(s)


def test_gix_plays_a_land_and_casts_a_spell_from_the_exiled_cards(cards):
    s = build(cards, OURS, theirs=["Lightning Bolt"])
    gix = put(s, "Gix, Yawgmoth Praetor")
    s.state.rules.controlled_since[gix.id].turn = 0
    for name in ("Island", "Lightning Bolt"):  # the top of Bob's library: the Bolt, then an Island
        c = card_named(s, name, "p2")
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
    bolt, island = card_named(s, "Lightning Bolt", "p2"), card_named(s, "Island", "p2")
    for _ in range(2):  # two cards to discard
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest")],
            to={"zone": "hand"})
    hand = [c for c in s.state.zones["p1:hand"] if s.state.cards[c].name == "Forest"][:2]
    mana(s, B=3, C=4)
    assert len(hand) == 2
    act(s, "p1", type="activate_ability", card_id=gix.id, ability=1, targets=["p2"], x_value=2)
    for _ in range(6):
        d = s.state.rules.decision
        if d is None:
            if s.state.zones.get("stack"):
                act(s, s.state.rules.priority, type="pass_priority")
                continue
            break
        if d.kind == "choose_cards" and "cast without paying" in d.prompt:
            break
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    assert {o.card_id for o in decision(s).options} == {bolt.id, island.id}  # the land (305.2a: a land play is left) and the spell
    pick_land = next(o.id for o in decision(s).options if o.card_id == island.id)
    act(s, "p1", type="choose", decision_id=decision(s).id, option_ids=[pick_land])
    # the same instruction goes on for the next card
    assert s.state.cards[island.id].zone == "p1:battlefield"  # (under Alice's control: she played it)
    d = decision(s)
    assert [o.card_id for o in d.options] == [bolt.id]
    other = reloaded(s)  # (a save and a load between the two)
    assert decision(other).id == d.id
    act(other, "p1", type="choose", decision_id=d.id, option_ids=[bolt.id])
    for _ in range(4):
        dd = other.state.rules.decision
        if dd is not None:
            act(other, "p1", type="choose", decision_id=dd.id, option_ids=[o.id for o in dd.options][: max(1, dd.min_choices)])
        else:
            break
    pass_until_stack_empty(other)
    assert other.state.cards[bolt.id].zone == "p2:graveyard"
    assert other.state.rules.lands_this_turn("p1", other.state.turn.number) == 1
    replay_matches(other)


def test_a_shock_land_asks_before_it_enters_and_survives_a_save(cards, settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    crypt = card("Blood Crypt", set_code="t28a", number="A6", type_line="Land — Swamp Mountain", color_identity=["B", "R"],
                 oracle_text="({T}: Add {B} or {R}.)\nAs Blood Crypt enters, you may pay 2 life. If you don't, it enters tapped.")
    build_database([*fixture_cards(), *REAL, crypt], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    try:
        s = build(repo, [*OURS, "Blood Crypt"])
        top = djinn_with_top(s, "Blood Crypt")
        pick(s, top.id)
        d = decision(s)  # 614.12a: pay 2 life or enter tapped, before it enters
        assert s.state.cards[top.id].zone == "p1:library" and "life" in d.prompt
        other = reloaded(s)  # (save and load while paused mid-choice)
        assert decision(other).id == d.id and other.state.cards[top.id].zone == "p1:library"
        act(other, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
        pass_until_stack_empty(other)
        c = other.state.cards[top.id]
        assert c.zone == "p1:battlefield" and not c.tapped
        assert other.state.players["p1"].life == 38
        assert other.state.rules.lands_this_turn("p1", other.state.turn.number) == 1
        replay_matches(other)
        assert reloaded(other).state.model_dump(mode="json") == other.state.model_dump(mode="json")
    finally:
        repo.close()
