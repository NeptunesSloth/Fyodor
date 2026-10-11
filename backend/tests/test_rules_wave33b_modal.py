"""Wave 33B: modal frames (CR 2026-09-25), real Oracle text (tests/fixtures/wave33b_modal_cards.json, from data/cards.sqlite).
Every scenario checks the replay and a save and a load.

* 607.2f / 614.12a / 400.7: "As this enchantment enters, choose Khans or Dragons." and a bulleted ability for each word (the Siege cycle). The
  words have no rules meaning; each bullet is an ability linked to the choice and works only for the word its object chose, as it entered. A
  new object (it left and came back) has made no choice.
* 700.2 / 700.2a / 601.2b: "Choose one. If [condition], [you may] choose both instead." is judged as the spell is cast; "Choose four. You may
  choose the same mode more than once."; lines about casting the spell ("This spell costs {2} less …") may come before the header.
* 700.2b / 603.3c / 608.2b: a mode of a modal triggered ability with "up to N target" (or several) targets.
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
from tests.wave9c_kit import build, card_named, check, life, mana, pt, put, reloaded, to_hand, zone_of

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave33b_modal_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w33b", number=f"M{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


def settle(s, prefer=(), limit=60):
    """Resolve everything; a decision is answered with the first of ``prefer`` it offers (card names or option ids), else its first options."""
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None:
            ids = [o.id for o in d.options]
            want = [o.id for p in prefer for o in d.options if p in (o.id, o.label, s.state.cards[o.card_id].name if o.card_id in s.state.cards else None)]
            pick = want[: max(1, d.min_choices)] if len(want) >= max(1, d.min_choices) else ids[: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=pick)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def cast(s, name, pid="p1", prefer=(), **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)
    settle(s, prefer)


def to_phase(s, phase, turn=None, limit=300):
    """Pass priority (no attackers, no blockers) until ``phase`` (of turn ``turn``) is reached."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.phase == phase and turn in (None, s.state.turn.number):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(f"never reached {phase} of turn {turn} (at {s.state.turn.phase} of turn {s.state.turn.number})")


def stops(s, *steps):
    """Alice is given priority in these steps of every turn (hers and the others')."""
    act(s, "p1", type="set_stops", own=list(steps), others=list(steps), smart_pass=False)


def choices(s, name, pid="p1"):
    return dict(s.state.cards[card_named(s, name, pid).id].choices)


# --- 607.2f: the Siege cycle ---------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("word", "bonus"), [("Temur", (3, 2)), ("Jeskai", (2, 2))])
def test_frostcliff_siege_static_belongs_to_temur_only(cards, word, bonus):
    """Frostcliff Siege: "As this enchantment enters, choose Jeskai or Temur. • Jeskai — Whenever one or more creatures you control deal combat
    damage to a player, draw a card. • Temur — Creatures you control get +1/+0 and have trample and haste." Only the chosen word's ability is there."""
    s = build(cards, ["Frostcliff Siege", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    to_hand(s, "Frostcliff Siege")
    mana(s, U=1, R=1, G=1)
    cast(s, "Frostcliff Siege", prefer=(word,))
    assert zone_of(s, "Frostcliff Siege") == "p1:battlefield"
    assert choices(s, "Frostcliff Siege") == {"Chosen word": word}
    assert pt(s, "Grizzly Bears") == bonus
    check(s)
    s = reloaded(s)
    assert choices(s, "Frostcliff Siege") == {"Chosen word": word}
    assert pt(s, "Grizzly Bears") == bonus  # (the choice is saved with the object: the loaded table reads the same word)


def _palace(cards, word):
    s = build(cards, ["Palace Siege", "Grizzly Bears"], forests=30, islands=30)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Palace Siege")
    mana(s, B=2, G=3)
    cast(s, "Palace Siege", prefer=(word,))
    assert zone_of(s, "Palace Siege") == "p1:battlefield"
    return s


def test_palace_siege_dragons_drains_at_your_upkeep_and_khans_does_not(cards):
    """Palace Siege: "• Khans — At the beginning of your upkeep, return target creature card from your graveyard to your hand. • Dragons — At the
    beginning of your upkeep, each opponent loses 2 life and you gain 2 life." Dragons drains; the Khans ability isn't there (the creature stays)."""
    s = _palace(cards, "Dragons")
    assert choices(s, "Palace Siege") == {"Chosen word": "Dragons"}
    stops(s, "upkeep")
    mine, theirs = life(s), life(s, "p2")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert (life(s), life(s, "p2")) == (mine + 2, theirs - 2)
    assert zone_of(s, "Grizzly Bears") == "p1:graveyard"
    check(s)
    s = reloaded(s)
    assert choices(s, "Palace Siege") == {"Chosen word": "Dragons"}
    to_phase(s, "upkeep", turn=5)
    settle(s)
    assert (life(s), life(s, "p2")) == (mine + 4, theirs - 4)  # (the loaded table reads the word too)


def test_palace_siege_khans_returns_a_creature_and_dragons_doesnt_drain(cards):
    s = _palace(cards, "Khans")
    stops(s, "upkeep")
    mine, theirs = life(s), life(s, "p2")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:hand"
    assert (life(s), life(s, "p2")) == (mine, theirs)
    check(s)


def test_a_siege_that_comes_back_is_a_new_object_with_its_own_choice(cards):
    """400.7: it left the battlefield, so the new object has made no choice yet (614.12a: it chooses again as it enters)."""
    s = _palace(cards, "Dragons")
    siege = card_named(s, "Palace Siege")
    act(s, "p1", type="move", card_ids=[siege.id], to={"zone": "hand"})
    assert choices(s, "Palace Siege") == {}
    mana(s, B=2, G=3)
    cast(s, "Palace Siege", prefer=("Khans",))
    assert choices(s, "Palace Siege") == {"Chosen word": "Khans"}
    stops(s, "upkeep")
    mine, theirs = life(s), life(s, "p2")
    to_phase(s, "upkeep", turn=3)
    settle(s)
    assert (life(s), life(s, "p2")) == (mine, theirs)  # (not the Dragons ability of the object before)
    assert zone_of(s, "Grizzly Bears") == "p1:hand"
    check(s)


def test_a_siege_put_onto_the_battlefield_by_hand_has_no_word_until_the_table_sets_it(cards):
    """Moved by hand it was not asked (the table tools make no choices); with no word recorded none of its linked abilities is there, and the
    table's own "Chosen word" entry stands in for the record, as a chosen color does."""
    s = build(cards, ["Frostcliff Siege", "Grizzly Bears"])
    put(s, "Grizzly Bears")
    siege = put(s, "Frostcliff Siege")
    assert s.state.rules.decision is None
    assert pt(s, "Grizzly Bears") == (2, 2)
    act(s, "p1", type="set_choice", card_id=siege.id, key="Chosen word", value="Temur")
    assert pt(s, "Grizzly Bears") == (3, 2)
    check(s)


# --- 700.2b / 603.3c: a mode of a modal triggered ability with "up to N target" targets ----------------------------------------------------


def _kami(cards, graveyard=("Grizzly Bears",), hold=False):
    s = build(cards, ["Kami of Restless Shadows", *{*graveyard}], forests=30, islands=30)
    for name in graveyard:
        act(s, "p1", type="move", card_ids=[card_named(s, name).id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Kami of Restless Shadows")
    if hold:
        stops(s, "main1")  # (Alice is given priority with the ability on the stack: the table can respond)
    mana(s, B=1, G=4)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kami of Restless Shadows").id)
    for _ in range(4):  # (the spell resolves; its enters trigger asks for a mode)
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    return s


def test_kami_offers_only_the_modes_that_can_be_chosen(cards):
    """Kami of Restless Shadows: "When this creature enters, choose one — • Return up to one target Ninja or Rogue creature card from your
    graveyard to your hand. • Put target creature card from your graveyard on top of your library." With no creature card in the graveyard the
    second mode has no legal target and can't be chosen (700.2b); the first needs none ("up to one")."""
    s = _kami(cards, graveyard=())
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == ["0:0"]
    settle(s)
    assert zone_of(s, "Kami of Restless Shadows") == "p1:battlefield"
    check(s)


def test_kami_second_mode_puts_the_creature_card_on_top_of_the_library(cards):
    s = _kami(cards)
    d = s.state.rules.decision
    assert d is not None and [o.id for o in d.options] == ["0:0", "1:0"]
    s = reloaded(s)  # (saved and loaded while the mode is being chosen)
    settle(s, prefer=("1:0", "Grizzly Bears"))
    assert s.state.zones["p1:library"][0] == card_named(s, "Grizzly Bears").id or s.state.zones["p1:library"][-1] == card_named(s, "Grizzly Bears").id
    assert zone_of(s, "Grizzly Bears") == "p1:library"
    check(s)


def test_kami_mode_whose_target_became_illegal_does_nothing(cards):
    """608.2b: its only target is gone when the ability resolves (exiled in response), so it doesn't resolve; the card stays where it went."""
    s = _kami(cards, hold=True)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["1:0"])
    d = s.state.rules.decision
    if d is not None:
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[next(o.id for o in d.options if o.card_id == card_named(s, "Grizzly Bears").id)])
    assert s.state.rules.stack  # (the ability is on the stack, its target chosen)
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "exile"})
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile"
    check(s)
    check(reloaded(s))


def test_daily_bugle_reporters_puts_a_counter_on_each_of_up_to_two_creatures(cards):
    """Daily Bugle Reporters: "• Puff Piece — Put a +1/+1 counter on each of up to two target creatures." (the mode's label is not text)."""
    s = build(cards, ["Daily Bugle Reporters", "Grizzly Bears", "Young Wolf"], forests=30, islands=30)
    put(s, "Grizzly Bears")
    put(s, "Young Wolf")
    to_hand(s, "Daily Bugle Reporters")
    mana(s, W=1, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Daily Bugle Reporters").id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["0:0"])  # the first mode …
    d = s.state.rules.decision
    assert (d.min_choices, d.max_choices) == (0, 2)  # … "up to two target creatures"
    act(s, d.player, type="choose", decision_id=d.id,
        option_ids=[o.id for o in d.options if s.state.cards[o.card_id].name in ("Grizzly Bears", "Young Wolf")])
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3) and pt(s, "Young Wolf") == (2, 2)
    check(s)
    check(reloaded(s))


def test_daily_bugle_reporters_a_target_that_became_illegal_is_not_affected(cards):
    """608.2b: one of the two targets is gone when the ability resolves; the other still gets its counter (the ability isn't countered, only
    when every target is illegal)."""
    s = build(cards, ["Daily Bugle Reporters", "Grizzly Bears", "Young Wolf"], forests=30, islands=30)
    put(s, "Grizzly Bears")
    wolf = put(s, "Young Wolf")
    to_hand(s, "Daily Bugle Reporters")
    stops(s, "main1")  # (Alice is given priority with the ability on the stack: the table can respond)
    mana(s, W=1, G=3)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Daily Bugle Reporters").id)
    for _ in range(4):
        if s.state.rules.decision is None:
            act(s, s.state.rules.priority, type="pass_priority")
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=["0:0"])
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id,
        option_ids=[o.id for o in d.options if s.state.cards[o.card_id].name in ("Grizzly Bears", "Young Wolf")])
    assert s.state.rules.stack
    act(s, "p1", type="move", card_ids=[wolf.id], to={"player": "p1", "zone": "exile"})
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3) and zone_of(s, "Young Wolf") == "p1:exile"
    check(s)
    check(reloaded(s))


# --- 700.2: modal spells ---------------------------------------------------------------------------------------------------------------


def test_soul_transfer_both_modes_only_with_an_artifact_and_an_enchantment(cards):
    """Soul Transfer: "Choose one. If you control an artifact and an enchantment as you cast this spell, you may choose both instead." The
    condition is judged as it is cast (601.2b): with only the artifact one mode is all there is, with both Alice may choose both."""
    s = build(cards, ["Soul Transfer", "Sol Ring", "Frostcliff Siege", "Young Wolf"], ["Grizzly Bears"], forests=30, islands=30)
    wolf = card_named(s, "Young Wolf")
    act(s, "p1", type="move", card_ids=[wolf.id], to={"player": "p1", "zone": "graveyard"})
    theirs = put(s, "Grizzly Bears", "p2")
    put(s, "Sol Ring")
    to_hand(s, "Soul Transfer")
    mana(s, B=2, G=1)
    soul = card_named(s, "Soul Transfer")
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=soul.id, modes=[0, 1], targets=[theirs.id, wolf.id])
    put(s, "Frostcliff Siege")
    act(s, "p1", type="cast_spell", card_id=soul.id, modes=[0, 1], targets=[theirs.id, wolf.id])
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:exile" and zone_of(s, "Young Wolf") == "p1:hand"
    check(s)
    check(reloaded(s))


def test_planewide_celebration_chooses_the_same_mode_four_times(cards):
    """Planewide Celebration: "Choose four. You may choose the same mode more than once." (700.2d): the mode counts as appearing that many times."""
    s = build(cards, ["Planewide Celebration"], forests=30, islands=30)
    to_hand(s, "Planewide Celebration")
    mana(s, G=7)
    celebration = card_named(s, "Planewide Celebration")
    with pytest.raises(ActionError, match="Choose 4 modes"):
        act(s, "p1", type="cast_spell", card_id=celebration.id, modes=[3, 3, 3])
    before = life(s)
    act(s, "p1", type="cast_spell", card_id=celebration.id, modes=[3, 3, 3, 3])
    settle(s)
    assert life(s) == before + 16
    check(s)
    check(reloaded(s))


def test_rally_the_monastery_reads_past_the_line_about_its_cost(cards):
    """Rally the Monastery: "This spell costs {2} less to cast if you've cast another spell this turn." comes before "Choose one —"; after
    another spell it costs {1}{W}."""
    s = build(cards, ["Rally the Monastery", "Lightning Bolt"], forests=30, islands=30)
    to_hand(s, "Lightning Bolt")
    to_hand(s, "Rally the Monastery")
    mana(s, R=1, W=1, G=1)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Lightning Bolt").id, targets=["p2"])
    settle(s)
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Rally the Monastery").id, modes=[0])
    settle(s)
    assert sum(c.name == "Monk" and c.zone == "p1:battlefield" for c in s.state.cards.values()) == 2
    check(s)
    check(reloaded(s))


def test_go_nuts_both_modes_when_cast_using_teamwork(cards):
    """Go Nuts!: "Teamwork 3 … Choose one. If this spell was cast using teamwork, choose both instead." (702.194b): paying the optional cost —
    tapping creatures with total power 3 — is what lets both modes be chosen."""
    s = build(cards, ["Go Nuts!", "Grizzly Bears", "Young Wolf"], ["Grizzly Bears"], forests=30, islands=30)
    mine = put(s, "Grizzly Bears")
    put(s, "Young Wolf")
    theirs = put(s, "Grizzly Bears", "p2")
    to_hand(s, "Go Nuts!")
    mana(s, G=1)
    go = card_named(s, "Go Nuts!")
    shape = {"modes": [0, 1], "targets": [mine.id, mine.id, theirs.id], "target_counts": [1, 1, 1]}
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=go.id, **shape)
    act(s, "p1", type="cast_spell", card_id=go.id, optional_costs=[f"{go.id}:teamwork"], **shape)
    d = s.state.rules.decision
    act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options])  # both creatures tap (total power 3)
    settle(s)
    assert pt(s, "Grizzly Bears") == (3, 3)  # (the counter first, 608.2c: it survives the fight with Bob's 2/2)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard"
    check(s)
    check(reloaded(s))


def test_kolaghans_command_a_mode_whose_target_became_illegal_does_nothing(cards):
    """Kolaghan's Command: "Choose two —" (it was automated before; this pins it). 608.2b: the creature card is gone when it resolves, so the
    first mode does nothing and the second one still happens."""
    s = build(cards, ["Kolaghan's Command", "Grizzly Bears"], forests=30, islands=30)
    bears = card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "graveyard"})
    to_hand(s, "Kolaghan's Command")
    act(s, "p1", type="set_prefs", hold_priority=True)  # (the table can respond: Alice keeps priority after casting)
    mana(s, B=1, R=1, G=1)
    before = life(s, "p2")
    act(s, "p1", type="cast_spell", card_id=card_named(s, "Kolaghan's Command").id, modes=[0, 3], targets=[bears.id, "p2"])
    assert s.state.rules.stack
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "exile"})
    settle(s)
    assert zone_of(s, "Grizzly Bears") == "p1:exile" and life(s, "p2") == before - 2
    check(s)
    check(reloaded(s))


def test_molten_collapse_both_modes_after_you_descended(cards):
    """Molten Collapse: "Choose one. If you descended this turn, you may choose both instead." (a permanent card was put into your graveyard
    this turn: history, read as the spell is cast)."""
    s = build(cards, ["Molten Collapse", "Grizzly Bears"], ["Grizzly Bears", "Sol Ring"], forests=30, islands=30)
    theirs = put(s, "Grizzly Bears", "p2")
    ring = put(s, "Sol Ring", "p2")
    to_hand(s, "Molten Collapse")
    mana(s, B=1, R=1)
    collapse = card_named(s, "Molten Collapse")
    shape = {"modes": [0, 1], "targets": [theirs.id, ring.id]}
    with pytest.raises(ActionError, match="Choose 1 mode"):
        act(s, "p1", type="cast_spell", card_id=collapse.id, **shape)
    act(s, "p1", type="move", card_ids=[card_named(s, "Grizzly Bears").id], to={"player": "p1", "zone": "graveyard"})
    act(s, "p1", type="cast_spell", card_id=collapse.id, **shape)
    settle(s)
    assert zone_of(s, "Grizzly Bears", "p2") == "p2:graveyard" and zone_of(s, "Sol Ring", "p2") == "p2:graveyard"
    check(s)
    check(reloaded(s))
