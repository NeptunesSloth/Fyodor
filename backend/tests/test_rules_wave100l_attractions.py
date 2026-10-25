"""Wave 100L: Attractions and tickets, real Oracle text (tests/fixtures/wave100l_cards.json, from data/cards.sqlite; an Attraction keeps its
printing: its lights are per collector number, app/rules/attractions100l.LIT). Every scenario checks the replay and a save and a load.

* 717.2, 103.3a: the deck's "Attractions" section is the player's hidden Attraction deck (``<pid>:attractions``, its count public).
* 701.51: "open an Attraction" puts its top card onto the battlefield; "Whenever you open an Attraction" (701.51c).
* 701.52a, 505.5, 702.159a: rolling to visit (the precombat main phase's turn-based action, or an effect) is a d6 roll; each Attraction with
  that number lit up is visited and its visit ability triggers; "the number of Attractions you've visited this turn".
* 702.159b: "claim the prize!" (Pick-a-Beeble); 717.6: an Attraction card goes to the command zone (its junkyard) instead of anywhere but
  the battlefield or exile.
* 107.17: "You get {TK}" is a ticket counter.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.factory import DeckCard, PlayerSetup, new_game
from app.game.session import GameSession
from app.game.views import build_view
from app.rules import coverage
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_wave12a_counters_keywords import rolls
from tests.wave9c_kit import card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave100l_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code=c.get("set", "w100l"), number=c.get("collector_number", f"L{i:03d}"),
              **{k: v for k, v in c.items() if k not in ("name", "set", "collector_number")}) for i, c in enumerate(DATA)]
REFUSED = ["Ferris Wheel", "Costume Shop", "Rest in Peace"]  # (Rest in Peace: a support card; the other two stay manual: see the module)


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


@pytest.mark.parametrize("name", [c["name"] for c in DATA if c["name"] not in REFUSED])
def test_the_cards_are_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL", name


@pytest.mark.parametrize("name", ["Ferris Wheel", "Costume Shop"])
def test_phasing_until_a_roll_and_stickers_stay_manual(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "PARTIAL"


def game(cards, mine=(), attractions=(), theirs=(), their_attractions=()):
    """Alice (p1) and Bob (p2); each Attraction deck in the order given, its top card last (not shuffled)."""
    def extra(names):
        return [DeckCard("attractions", 1, (c := cards.resolve(n))["name"], c["id"]) for n in names]

    alice = deck(cards, "Krenko, Mob Boss", [*((1, n) for n in mine), (9, "Swamp"), (9, "Forest")]) + extra(attractions)
    bob = deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in theirs), (10, "Island")]) + extra(their_attractions)
    s = GameSession(enable(new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False)), cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def settle(s, *picks, limit=60):
    """Resolve the stack; decisions answered from ``picks`` in turn (an option id or a list of ids), else with their first options."""
    picks = list(picks)
    for _ in range(limit):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            pick = picks.pop(0) if picks else None
            ids = [pick] if isinstance(pick, str) else pick or [o.id for o in d.options][: max(1, d.min_choices)]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def to_main(s, turn, limit=400):
    """Pass priority (no attackers, no blockers) until the precombat main phase of ``turn`` has begun and its triggers resolved."""
    for _ in range(limit):
        d = s.state.rules.decision
        if s.state.turn.number == turn and s.state.turn.phase == "main1" and d is None and not s.state.zones.get("stack"):
            return
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            act(s, d.player, type=d.kind, **({"attackers": []} if d.kind == "declare_attackers" else {"blocks": []}))
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError("never reached that main phase")


def deck_of(s, pid="p1"):
    return list(s.state.zones.get(f"{pid}:attractions", []))


def cast(s, name, pid="p1", **kw):
    act(s, pid, type="cast_spell", card_id=card_named(s, name, pid).id, **kw)


def zone(s, name, pid="p1"):
    return s.state.cards[card_named(s, name, pid).id].zone


# -- the Attraction deck (717.2) --------------------------------------------------------------------------------------------------------
def test_the_attractions_section_is_read_written_and_checked(cards):
    from app.decks import service
    from app.decks.models import DeckEntry, DeckIn
    from app.decks.parser import format_deck_text, parse_deck_text

    parsed = parse_deck_text("Commander\n1 Krenko, Mob Boss\n\nDeck\n1 Deadbeat Attendant\n\nAttractions\n1 Pick-a-Beeble (UNF) 223a\n1 Information Booth\n")
    got = [(e.section, e.name, e.set_code, e.collector_number) for e in parsed.entries]
    assert got[-2:] == [("attractions", "Pick-a-Beeble", "unf", "223a"), ("attractions", "Information Booth", None, None)]
    text = format_deck_text([{"section": e.section, "quantity": e.quantity, "name": e.name, "set_code": e.set_code,
                              "collector_number": e.collector_number} for e in parsed.entries])
    assert "Attractions\n1 Pick-a-Beeble (UNF) 223a\n" in text
    from app.decks.parser import section_for_categories

    assert section_for_categories(["Attractions"]) == "attractions"  # (an Archidekt category)
    entries = [DeckEntry(section="attractions", quantity=1, name=n, printing_id=cards.resolve(n)["id"]) for n in ("Pick-a-Beeble", "Trash Bin")]
    data = {e.printing_id: cards.resolve(e.name) for e in entries}
    warnings = [w.message for w in service.validate(DeckIn(name="d", entries=entries), cards, data)]
    assert any("717.2a" in w for w in warnings)  # (fewer than ten)


def test_the_attraction_deck_is_hidden_and_opening_makes_the_card_public(cards):
    s = game(cards, ["Deadbeat Attendant", "The Most Dangerous Gamer"], ["Trash Bin", "Information Booth", "Clown Extruder"])
    hidden = deck_of(s)
    for viewer in ("p1", "p2"):
        view = build_view(s.state, viewer)
        assert view["zones"]["p1:attractions"] == {"count": 3, "known": []}
        assert not set(hidden) & set(view["cards"])
    put(s, "The Most Dangerous Gamer")
    to_hand(s, "Deadbeat Attendant")
    mana(s, B=1, C=1)
    cast(s, "Deadbeat Attendant")
    settle(s)
    booth = card_named(s, "Clown Extruder")  # 701.51b: the top card (the last one here)
    assert s.state.cards[booth.id].zone == "p1:battlefield" and deck_of(s) == hidden[:2]
    assert s.state.cards[card_named(s, "The Most Dangerous Gamer").id].counters.get("+1/+1") == 1  # 701.51c
    assert booth.id in build_view(s.state, "p2")["cards"]
    check(s)


def test_open_two_and_an_empty_attraction_deck(cards):
    s = game(cards, ["Step Right Up", "The Most Dangerous Gamer"], ["Trash Bin", "Information Booth"], their_attractions=["Fortune Teller"])
    put(s, "The Most Dangerous Gamer")
    to_hand(s, "Step Right Up")
    mana(s, B=1, C=3)
    cast(s, "Step Right Up")
    settle(s)
    assert zone(s, "Trash Bin") == zone(s, "Information Booth") == "p1:battlefield" and deck_of(s) == []
    assert s.state.cards[card_named(s, "The Most Dangerous Gamer").id].counters.get("+1/+1") == 2
    assert zone(s, "Fortune Teller", "p2") == "p2:attractions"  # (only your own deck)
    act(s, "p1", type="move", card_ids=[card_named(s, "Step Right Up").id], to={"zone": "hand"})
    mana(s, B=1, C=3)
    cast(s, "Step Right Up")
    settle(s)  # 701.51a: nothing left to open: nothing happens
    assert s.state.cards[card_named(s, "The Most Dangerous Gamer").id].counters.get("+1/+1") == 2
    check(s)


# -- rolling to visit (701.52, 505.5, 702.159) ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("die,drawn,robots,drained", [(2, 1, 0, 1), (5, 0, 1, 0), (6, 1, 1, 0), (3, 0, 0, 0)])
def test_the_precombat_main_phase_rolls_to_visit(cards, monkeypatch, die, drawn, robots, drained):
    rolls(monkeypatch, die)
    s = game(cards, ["Dee Kay, Finder of the Lost"], ["Information Booth", "Clown Extruder"])  # 218a: 2 and 6 lit; 204d: 5 and 6
    for name in ("Information Booth", "Clown Extruder", "Dee Kay, Finder of the Lost"):
        put(s, name)
    hand = len(s.state.zones["p1:hand"])
    to_main(s, 3)  # (Bob's turn rolls nothing: he controls no Attraction)
    assert len(s.state.zones["p1:hand"]) == hand + 1 + drawn  # (Alice's draw step, then the visit)
    assert sum(1 for c in s.state.cards.values() if c.name == "Clown Robot" and c.zone == "p1:battlefield") == robots
    assert s.state.players["p2"].life == 40 - drained  # (Dee Kay: "Whenever you roll a 2": the roll to visit is a die roll, 706)
    check(s)


def test_no_attraction_no_roll(cards, monkeypatch):
    rolls(monkeypatch)  # (any roll would fail: the queue is empty)
    s = game(cards, ["Dee Kay, Finder of the Lost"], ["Information Booth"])
    put(s, "Dee Kay, Finder of the Lost")
    to_main(s, 3)
    check(s)


def play(s, *, want=(), limit=40):
    """Resolve the stack; each decision is answered with the first option whose label or card is in ``want``, else the first option."""
    seen = []
    for _ in range(limit):
        d = s.state.rules.decision
        if (d is None and not s.state.zones.get("stack")) or (d is not None and d.kind in ("declare_attackers", "declare_blockers")):
            return seen
        if d is not None:
            seen.append((d.kind, d.prompt, [(o.id, o.label) for o in d.options]))
            ids = [o.id for o in d.options if o.id in want or o.card_id in want or any(w in (o.label or "") for w in want if isinstance(w, str))]
            ids += [o.id for o in d.options if o.id not in ids]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=ids[: max(1, d.min_choices)])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    raise AssertionError(seen)


# -- the junkyard (717.6) ---------------------------------------------------------------------------------------------------------------
def test_a_destroyed_attraction_goes_to_its_owners_junkyard(cards):
    s = game(cards, ["Draconian Gate-Bot"], their_attractions=["Kiddie Coaster"])
    coaster = put(s, "Kiddie Coaster", "p2")
    to_hand(s, "Draconian Gate-Bot")
    mana(s, C=5)
    cast(s, "Draconian Gate-Bot")
    seen = play(s, want=("Destroy", coaster.id))
    assert zone(s, "Kiddie Coaster", "p2") == "p2:command", seen  # not the graveyard: 717.6
    assert not s.state.zones.get("p2:graveyard")
    check(s)


def test_rest_in_peace_or_the_junkyard_its_owner_chooses(cards):
    s = game(cards, ["Draconian Gate-Bot", "Rest in Peace"], their_attractions=["Kiddie Coaster"])
    coaster = put(s, "Kiddie Coaster", "p2")
    put(s, "Rest in Peace")
    to_hand(s, "Draconian Gate-Bot")
    mana(s, C=5)
    cast(s, "Draconian Gate-Bot")
    seen = play(s, want=("Destroy", coaster.id, "717.6"))
    # 616.1: two replacements with different results (exile, the command zone): the affected object's controller chooses
    asked = [options for _, prompt, options in seen if "Rest in Peace: Exile it" in {label for _, label in options}]
    assert len(asked) == 1 and {o for o, _ in asked[0]} == {"exile", "command"} and s.state.cards[coaster.id].owner == "p2"
    assert zone(s, "Kiddie Coaster", "p2") == "p2:command"
    check(s)


def bears(s, pid, n):
    from tests.test_rules_conditionals import creature

    return [creature(s, pid, f"Bear {pid} {k}") for k in range(n)]


# -- "roll to visit your Attractions" as an effect; "Whenever you roll to visit …, if you roll a 6" ---------------------------------------
@pytest.mark.parametrize("die", [6, 5])
def test_line_cutter_rolls_and_the_pass_holder_comes_back_on_a_six(cards, monkeypatch, die):
    rolls(monkeypatch, die)
    s = game(cards, ["Line Cutter", '"Lifetime" Pass Holder', "Lightning Bolt"], ["Information Booth", "Clown Extruder"],
             their_attractions=["Clown Extruder"])
    put(s, "Clown Extruder", "p2")  # (Bob's: not visited by Alice's roll)
    holder = put(s, '"Lifetime" Pass Holder')
    to_hand(s, "Lightning Bolt")
    mana(s, R=1)
    cast(s, "Lightning Bolt", targets=[holder.id])
    play(s)  # 700.4: it dies: open an Attraction
    assert zone(s, '"Lifetime" Pass Holder') == "p1:graveyard" and zone(s, "Clown Extruder") == "p1:battlefield"
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s, want=("yes",))
    back = s.state.cards[holder.id]
    assert (back.zone, back.tapped) == (("p1:battlefield", True) if die == 6 else ("p1:graveyard", False))  # (it enters tapped)
    assert [c.controller for c in s.state.cards.values() if c.name == "Clown Robot"] == ["p1"]  # 204d: 5 and 6 are lit
    check(s)


# -- "claim the prize!" (702.159b) ------------------------------------------------------------------------------------------------------
def test_pick_a_beeble_claims_the_prize(cards, monkeypatch):
    rolls(monkeypatch, 5, 1)  # (the roll to visit: 223c has 2, 5 and 6 lit; then Pick-a-Beeble's own die)
    s = game(cards, ["Line Cutter", "The Most Dangerous Gamer"], ["Information Booth", "Pick-a-Beeble"])
    beeble = put(s, "Pick-a-Beeble")
    act(s, "p1", type="counter", card_ids=[beeble.id], kind="luck", delta=5)
    put(s, "The Most Dangerous Gamer")
    victim, = bears(s, "p2", 1)
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s, want=(victim.id,))
    assert zone(s, "Pick-a-Beeble") == "p1:command"  # sacrificed: into its owner's junkyard (717.6)
    assert sum(1 for c in s.state.cards.values() if c.name == "Treasure" and c.zone == "p1:battlefield") == 3
    assert zone(s, "Information Booth") == "p1:battlefield"  # (then open an Attraction)
    assert victim.id not in s.state.cards or s.state.cards[victim.id].zone != "p2:battlefield"  # "Whenever you claim the prize …"
    assert s.state.cards[card_named(s, "The Most Dangerous Gamer").id].counters.get("+1/+1") == 1
    check(s)


def test_no_prize_below_six_luck_counters(cards, monkeypatch):
    rolls(monkeypatch, 2, 3)
    s = game(cards, ["Line Cutter", "The Most Dangerous Gamer"], ["Information Booth", "Pick-a-Beeble"])
    beeble = put(s, "Pick-a-Beeble")
    bears(s, "p2", 1)
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s)
    assert s.state.cards[beeble.id].zone == "p1:battlefield" and s.state.cards[beeble.id].counters.get("luck") == 3
    assert zone(s, "Information Booth") == "p1:attractions"
    check(s)


# -- "the Attractions you've visited this turn" (each once) ------------------------------------------------------------------------------
def test_visited_attractions_size_black_hole_and_make_soul_swindler_indestructible(cards, monkeypatch):
    from app.game.errors import ActionError

    rolls(monkeypatch, 6, 6)
    s = game(cards, ["Line Cutter", "Soul Swindler", "Black Hole"], ["Information Booth", "Clown Extruder"])
    put(s, "Information Booth")
    put(s, "Clown Extruder")
    swindler = put(s, "Soul Swindler")
    to_main(s, 3)  # the turn-based roll: both visited
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s)  # visited again: still two Attractions
    them = bears(s, "p2", 3)
    to_hand(s, "Black Hole")
    mana(s, B=1, C=3)
    with pytest.raises(ActionError):
        cast(s, "Black Hole", targets=[swindler.id, *(b.id for b in them)], target_counts=[1, 3])
    cast(s, "Black Hole", targets=[swindler.id, them[0].id, them[1].id], target_counts=[1, 2])
    play(s)
    assert s.state.cards[swindler.id].zone == "p1:battlefield"  # indestructible: Alice visited an Attraction this turn
    assert [b.id in s.state.cards and s.state.cards[b.id].zone == "p2:battlefield" for b in them] == [False, False, True]
    check(s)


def test_storybook_ride_exiles_by_the_visits_and_puts_the_rest_on_the_bottom(cards, monkeypatch):
    rolls(monkeypatch, 6)
    s = game(cards, ["Line Cutter"], ["Information Booth", "Storybook Ride"])  # 229b: 3, 4 and 6 lit
    put(s, "Storybook Ride")
    put(s, "Information Booth")
    to_hand(s, "Line Cutter")
    top = s.state.zones["p1:library"][:3]
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s, want=("Storybook Ride",))  # (Storybook Ride resolves after Information Booth: X = 2 either way)
    exiled = [c for c in s.state.zones["p1:exile"]]
    assert len(exiled) == 2 and set(exiled) <= set(top)
    assert {s.state.cards[c].name for c in exiled} == {"Swamp"}
    act(s, "p1", type="play_land", card_id=exiled[0])  # (you may play those cards this turn)
    to_main(s, 2)  # through the end step
    assert s.state.cards[exiled[0]].zone == "p1:battlefield"
    assert s.state.zones["p1:library"][-1] == exiled[1]  # the one still exiled: on the bottom
    check(s)


def test_motion_sickness_follows_a_visit_to_a_tapped_creature(cards, monkeypatch):
    rolls(monkeypatch, 2)
    s = game(cards, ["Line Cutter", "Motion Sickness"], ["Information Booth"])
    put(s, "Information Booth")
    first, second = bears(s, "p2", 2)
    to_hand(s, "Motion Sickness")
    mana(s, U=1, C=3)
    cast(s, "Motion Sickness", targets=[first.id])
    play(s)
    aura = card_named(s, "Motion Sickness")
    assert s.state.cards[aura.id].attached_to == first.id and s.state.cards[first.id].tapped
    act(s, "p2", type="tap", card_ids=[second.id])
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s, want=(second.id, "yes"))
    assert s.state.cards[aura.id].attached_to == second.id
    check(s)


def test_squirrel_squatters_attack_with_a_squirrel_per_visited_attraction(cards, monkeypatch):
    rolls(monkeypatch, 6)
    s = game(cards, ["Squirrel Squatters"], ["Information Booth", "Clown Extruder"])
    to_hand(s, "Squirrel Squatters")
    mana(s, G=2, C=3)
    cast(s, "Squirrel Squatters")
    play(s)  # opens Clown Extruder
    put(s, "Information Booth")
    to_main(s, 3)  # both visited
    from tests.test_rules_wave100f_attached import to_phase

    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": card_named(s, "Squirrel Squatters").id, "target": "p2"}])
    play(s)
    squirrels = [c for c in s.state.cards.values() if c.name == "Squirrel" and c.zone == "p1:battlefield"]
    assert len(squirrels) == 2 and all(c.tapped for c in squirrels)
    assert s.state.players["p2"].life == 40 - 4 - 2  # (the two Squirrels attacked too: 508.4)
    check(s)


# -- the other visit abilities: all lit on a 6 ------------------------------------------------------------------------------------------
def test_every_attraction_is_visited_on_a_six(cards, monkeypatch):
    rolls(monkeypatch, 6)
    names = ["Clown Extruder", "Concession Stand", "Kiddie Coaster", "Roller Coaster", "Fortune Teller", "Spinny Ride", "Foam Weapons Kiosk",
             "Bumper Cars", "Trash Bin", "Balloon Stand"]
    s = game(cards, ["Line Cutter"], names)
    for n in names:
        put(s, n)
    foe, = bears(s, "p2", 1)
    mine, = bears(s, "p1", 1)
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    play(s, want=(foe.id, mine.id))
    on = [c.name for c in s.state.cards.values() if c.zone == "p1:battlefield" and c.is_token and c.id != mine.id]
    assert sorted(on) == ["Balloon", "Clown Robot", "Food"]
    assert s.state.cards[foe.id].tapped and s.state.cards[mine.id].counters.get("+1/+1") == 1
    from tests.wave9c_kit import pt

    assert pt(s, "Line Cutter")[0] == 3 + 1 + 2  # Kiddie Coaster and Roller Coaster
    assert len(s.state.zones["p1:graveyard"]) == 1  # Trash Bin: milled two, one of them back to the hand
    check(s)


@pytest.mark.parametrize("die", [2, 3, 5])  # 216a: 2 and 6 lit; 217a: 3 and 6; 222b: 5 and 6
def test_hall_of_mirrors_haunted_house_and_merry_go_round(cards, monkeypatch, die):
    from app.rules.plan import Plan

    rolls(monkeypatch, die)
    s = game(cards, ["Line Cutter", "Deadbeat Attendant"], ["Hall of Mirrors", "Haunted House", "Merry-Go-Round"])
    for n in ("Hall of Mirrors", "Haunted House", "Merry-Go-Round"):
        put(s, n)
    dead = card_named(s, "Deadbeat Attendant")
    act(s, "p1", type="move", card_ids=[dead.id], to={"zone": "graveyard"})
    bear, = bears(s, "p1", 1)
    to_hand(s, "Line Cutter")
    mana(s, B=1, C=3)
    cast(s, "Line Cutter")
    cutter = card_named(s, "Line Cutter")
    play(s, want=(cutter.id, dead.id))
    plan = Plan(s.state, "p1", s.cards, None)
    if die == 2:  # the bear is a copy of Line Cutter until end of turn
        assert plan.ch(s.state.cards[bear.id]).name == "Line Cutter"
    if die == 3:  # back with haste, exiled at Alice's end step
        assert s.state.cards[dead.id].zone == "p1:battlefield" and "haste" in plan.ch(s.state.cards[dead.id]).keywords
        to_main(s, 2)
        assert s.state.cards[dead.id].zone == "p1:exile"
    if die == 5:  # the 2/2 bear has horsemanship, Line Cutter (3/4) hasn't
        assert "horsemanship" in plan.ch(s.state.cards[bear.id]).keywords
        assert "horsemanship" not in plan.ch(s.state.cards[cutter.id]).keywords
    check(s)


# -- tickets (107.17) --------------------------------------------------------------------------------------------------------------------
def test_you_get_a_ticket_counter(cards):
    s = game(cards, ["Blorbian Buddy", "Ticket Turbotubes"])
    buddy = put(s, "Blorbian Buddy")
    tubes = put(s, "Ticket Turbotubes")
    mana(s, C=3)
    act(s, "p1", type="activate_ability", card_id=tubes.id, ability=1)
    play(s)
    assert s.state.players["p1"].resources.get("ticket") == 1
    to_main(s, 3)  # (Blorbian Buddy: no longer summoning sick)
    mana(s, G=1)
    act(s, "p1", type="activate_ability", card_id=buddy.id, ability=1)
    play(s)
    assert s.state.players["p1"].resources.get("ticket") == 2
    check(s)
