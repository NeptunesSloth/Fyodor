"""Wave 31C: copies of permanents (CR 707.2-707.4, 707.9, 613.2, 500.4), real Oracle text
(tests/fixtures/wave31c_copy_cards.json, from data/cards.sqlite). Every scenario checks the replay and a save and a load.

* 611.2a / 500.4: "Until your next turn, ~ becomes a copy of …" (Volrath, Absorbing Man) and the duration in front of the sentence ("Until end of turn,
  Oko becomes a copy …"); a token made from the copy takes the copiable values (707.2, 707.3) — the exceptions with them (707.9a-b) — and none of
  the duration, which belongs to the first copy effect alone.
* 707.4 / 115.1: "Target artifact you control becomes a copy of a second / another target artifact …" (Shuri, Saheeli): both are targets;
  "another" is a different object (115.3); "except it isn't legendary" (707.9b) keeps the legend rule (704.5j) from removing the copy.
* 707.9a: "it has Sakashima's other abilities" is Partner and the legend-rule line: a copy of a legendary creature with it keeps both.
* 111.4 / 707.2: "For each artifact you control, create a token that's a copy of it. Those tokens gain haste. Exile those tokens …" and
  "for each other nonland permanent you control" (other than the source); a plural name's "if they're not a token … copies of them" (The Notary Hobbits);
  a granted "When this token dies" (Jaxis)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.cards.images import ImageStore
from app.cards.importer import build_database
from app.cards.repository import CardRepository
from app.game.errors import ActionError
from app.rules import coverage, scripts
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.wave9c_kit import build, card_named, check, mana, put, to_hand

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave31c_copy_cards.json").read_text("utf-8"))
KNOWN = {c["name"] for c in fixture_cards()}
EXTRA = [card(c["name"], set_code="w31c", number=f"C{i:02d}", **{k: v for k, v in c.items() if k != "name"})
         for i, c in enumerate(DATA) if c["name"] not in KNOWN]


@pytest.fixture()
def cards(settings):
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


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


def to_phase(s, phase, turn=None, limit=200):
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
    act(s, "p1", type="set_stops", own=list(steps), others=list(steps), smart_pass=False)


def chars(s, c):
    return Plan(s.state, c.controller, s.cards, None).ch(s.state.cards[c.id])


def ab(s, c, do):
    """The index of the ability whose effects do ``do``."""
    return next(i for i, d in scripts.definitions(chars(s, c)).items() if any(e.get("do") == do for e in d.get("effects") or []))


def tokens(s, name=None):
    return [c for c in s.state.cards.values() if c.is_token and c.zone.endswith("battlefield") and name in (None, chars(s, c).name)]


def counter(s, c, kind, delta):
    act(s, "p1", type="counter", card_ids=[c.id], kind=kind, delta=delta)


def seasoned(s, *cs):
    """These creatures have been on the table since before the turn began (302.6: they may use {T} abilities)."""
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


@pytest.mark.parametrize("name", [c["name"] for c in DATA])
def test_every_card_is_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# --- "Until your next turn" (500.4) and the copy of a copy (707.3) --------------------------------------------------------------


def test_volrath_is_a_7_5_copy_until_his_next_turn_and_a_token_copy_of_it_keeps_the_exceptions_for_good(cards):
    s = build(cards, ["Volrath, the Shapestealer", "Grizzly Bears", "Cackling Counterpart"], [])
    volrath, bears = put(s, "Volrath, the Shapestealer"), put(s, "Grizzly Bears")
    counter(s, bears, "+1/+1", 1)  # ("target creature with a counter on it")
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=volrath.id, ability=ab(s, volrath, "become_copy"), targets=[bears.id])
    settle(s)
    c = chars(s, volrath)
    assert (c.name, c.pt, set(c.subtypes)) == ("Grizzly Bears", (7, 5), {"Bear"})  # 707.9b: the copy is 7/5, not the Bears' 2/2 (nor its counter)
    assert ab(s, volrath, "become_copy") is not None  # 707.9a: "except it has this ability" — the copy can do it again
    check(s)
    cc = to_hand(s, "Cackling Counterpart")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=cc.id, targets=[volrath.id])
    settle(s)
    [tok] = [t for t in tokens(s, "Grizzly Bears") if chars(s, t).pt == (7, 5)]  # 707.3: a copy of the copy starts from the first copy's values
    assert ab(s, tok, "become_copy") is not None
    check(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=2)
    assert chars(s, volrath).pt == (7, 5)  # (Bob's turn: still Alice's "until your next turn")
    to_phase(s, "upkeep", turn=3)
    assert chars(s, volrath).name == "Volrath, the Shapestealer"  # 500.4: Alice's own next turn began
    assert chars(s, tok).pt == (7, 5) and chars(s, tok).name == "Grizzly Bears"  # the token keeps the values (the duration was never part of them)
    check(s)


def test_scion_of_the_ur_dragon_becomes_a_copy_of_the_dragon_it_put_into_the_graveyard_until_end_of_turn(cards):
    s = build(cards, ["Scion of the Ur-Dragon", "Shivan Dragon"], [])
    scion = put(s, "Scion of the Ur-Dragon")
    mana(s, C=2)
    act(s, "p1", type="activate_ability", card_id=scion.id, ability=ab(s, scion, "become_copy"))
    settle(s, prefer=["Shivan Dragon"])
    c = chars(s, scion)
    assert c.name == "Shivan Dragon" and c.pt == (5, 5) and "flying" in c.keywords  # 707.2: the printed values of a card in a graveyard
    assert card_named(s, "Shivan Dragon").zone == "p1:graveyard"
    check(s)
    stops(s, "end")
    to_phase(s, "cleanup")
    assert chars(s, scion).name == "Scion of the Ur-Dragon"
    check(s)


def test_oko_the_trickster_becomes_a_copy_with_the_duration_in_front_of_the_sentence(cards):
    s = build(cards, ["Oko, the Trickster", "Grizzly Bears"], [])
    oko, bears = put(s, "Oko, the Trickster"), put(s, "Grizzly Bears")
    counter(s, oko, "loyalty", 4)
    act(s, "p1", type="activate_ability", card_id=oko.id, ability=ab(s, oko, "become_copy"), targets=[bears.id])
    settle(s)
    c = chars(s, oko)
    assert c.name == "Grizzly Bears" and c.pt == (2, 2) and "Planeswalker" not in c.types  # 707.2: only the copiable values — no loyalty ability, no PW type
    check(s)
    stops(s, "end")
    to_phase(s, "cleanup")
    assert chars(s, oko).name == "Oko, the Trickster"  # until end of turn
    check(s)


def test_absorbing_man_is_a_legendary_4_4_land_copy_with_his_own_name_until_his_next_turn(cards):
    s = build(cards, ["Absorbing Man"], [])
    man = put(s, "Absorbing Man")
    forest = next(c for c in s.state.cards.values() if c.owner == "p1" and c.name == "Forest" and c.zone == "p1:battlefield") \
        if any(c.name == "Forest" and c.zone == "p1:battlefield" for c in s.state.cards.values()) else put(s, "Forest")
    stops(s, "main1")
    to_phase(s, "main1", turn=3)
    settle(s, prefer=[forest.id])
    c = chars(s, man)
    assert c.name == "Absorbing Man" and "Legendary" in c.supertypes and {"Land", "Creature"} <= set(c.types)
    assert {"Forest", "Human", "Villain"} <= set(c.subtypes) and c.pt == (4, 4) and "vigilance" in c.keywords  # 707.9b
    check(s)


# --- two targets (115.1, 115.3, 707.4) ----------------------------------------------------------------------------------------------


def test_shuri_makes_an_artifact_a_copy_that_is_not_legendary_so_the_legend_rule_leaves_all_of_them(cards):
    s = build(cards, ["Shuri, Wakandan Inventor", "Sol Ring", "Karn, Silver Golem", "Cackling Counterpart"], [])
    shuri, ring, karn = put(s, "Shuri, Wakandan Inventor"), put(s, "Sol Ring"), put(s, "Karn, Silver Golem")
    seasoned(s, shuri)
    mana(s, C=1)
    act(s, "p1", type="activate_ability", card_id=shuri.id, ability=ab(s, shuri, "become_copy"), targets=[ring.id, karn.id], target_counts=[1, 1])
    settle(s)
    c = chars(s, ring)
    assert c.name == "Karn, Silver Golem" and "Legendary" not in c.supertypes and "Creature" in c.types and c.pt == (4, 4)  # 707.9b
    assert chars(s, karn).supertypes == frozenset({"Legendary"})
    assert s.state.cards[ring.id].zone == "p1:battlefield" and s.state.cards[karn.id].zone == "p1:battlefield"  # 704.5j: only one of them is legendary
    check(s)
    cc = to_hand(s, "Cackling Counterpart")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=cc.id, targets=[ring.id])
    settle(s)
    [tok] = tokens(s, "Karn, Silver Golem")
    assert "Legendary" not in chars(s, tok).supertypes and s.state.cards[karn.id].zone == "p1:battlefield"  # 707.3: the copy of the copy isn't legendary either
    check(s)


def test_the_animus_makes_a_legendary_creature_a_copy_of_a_card_in_exile_until_its_next_turn(cards):
    s = build(cards, ["The Animus", "Grizzly Bears"], [])
    animus, krenko, bears = put(s, "The Animus"), put(s, "Krenko, Mob Boss"), card_named(s, "Grizzly Bears")
    act(s, "p1", type="move", card_ids=[bears.id], to={"player": "p1", "zone": "exile"})
    counter(s, bears, "memory", 1)
    act(s, "p1", type="activate_ability", card_id=animus.id, ability=ab(s, animus, "become_copy"), targets=[krenko.id, bears.id], target_counts=[1, 1])
    settle(s)
    c = chars(s, krenko)
    assert c.name == "Grizzly Bears" and c.pt == (2, 2) and "Legendary" not in c.supertypes  # 707.2: the printed values of the card in exile
    assert s.state.cards[bears.id].zone == "p1:exile"
    check(s)
    stops(s, "upkeep")
    to_phase(s, "upkeep", turn=3)
    assert chars(s, krenko).name == "Krenko, Mob Boss"
    check(s)


def test_saheeli_sublime_artificer_needs_two_different_targets_and_adds_artifact(cards):
    s = build(cards, ["Saheeli, Sublime Artificer", "Sol Ring", "Grizzly Bears"], [])
    saheeli, ring, bears = put(s, "Saheeli, Sublime Artificer"), put(s, "Sol Ring"), put(s, "Grizzly Bears")
    counter(s, saheeli, "loyalty", 5)
    idx = ab(s, saheeli, "become_copy")
    with pytest.raises(ActionError):
        act(s, "p1", type="activate_ability", card_id=saheeli.id, ability=idx, targets=[ring.id, ring.id], target_counts=[1, 1])  # "another target": 115.3
    act(s, "p1", type="activate_ability", card_id=saheeli.id, ability=idx, targets=[ring.id, bears.id], target_counts=[1, 1])
    settle(s)
    c = chars(s, ring)
    assert c.name == "Grizzly Bears" and {"Artifact", "Creature"} <= set(c.types) and c.pt == (2, 2) and "Bear" in c.subtypes  # 707.9b: "in addition"
    check(s)


# --- "its other abilities" (707.9a) ---------------------------------------------------------------------------------------------------


def test_sakashima_enters_as_a_copy_of_krenko_and_keeps_partner_and_the_legend_rule_line(cards):
    s = build(cards, ["Sakashima of a Thousand Faces", "Cackling Counterpart"], [])
    krenko = put(s, "Krenko, Mob Boss")
    sak = to_hand(s, "Sakashima of a Thousand Faces")
    mana(s, U=1, C=3)
    act(s, "p1", type="cast_spell", card_id=sak.id)
    settle(s, prefer=[krenko.id, "Yes"])
    c = chars(s, sak)
    assert c.name == "Krenko, Mob Boss" and "Legendary" in c.supertypes and c.pt == chars(s, krenko).pt
    texts = [a.text for a in c.abilities]
    assert any(t == "Partner" for t in texts) and any("legend rule" in t for t in texts)  # 707.9a: Sakashima's other abilities
    assert s.state.cards[krenko.id].zone == "p1:battlefield" and s.state.cards[sak.id].zone == "p1:battlefield"  # 704.5j doesn't apply
    check(s)
    cc = to_hand(s, "Cackling Counterpart")
    mana(s, U=2, C=1)
    act(s, "p1", type="cast_spell", card_id=cc.id, targets=[sak.id])
    settle(s)
    assert len([c for c in s.state.cards.values() if chars(s, c).name == "Krenko, Mob Boss" and c.zone == "p1:battlefield"]) == 3
    check(s)


# --- a token copy of each (111.4, 608.2h) ---------------------------------------------------------------------------------------


def test_saheeli_the_gifted_copies_each_artifact_with_haste_and_exiles_the_tokens_at_the_end_step(cards):
    s = build(cards, ["Saheeli, the Gifted", "Sol Ring", "Arcane Signet"], [])
    saheeli, ring, signet = put(s, "Saheeli, the Gifted"), put(s, "Sol Ring"), put(s, "Arcane Signet")
    counter(s, saheeli, "loyalty", 8)
    act(s, "p1", type="activate_ability", card_id=saheeli.id, ability=ab(s, saheeli, "token_copy"))
    settle(s)
    made = tokens(s)
    assert sorted(chars(s, t).name for t in made) == ["Arcane Signet", "Sol Ring"] and all("haste" in chars(s, t).keywords for t in made)
    check(s)
    stops(s, "end")
    to_phase(s, "end", turn=1)
    settle(s)
    assert not tokens(s) and all(s.state.cards[c].zone == "p1:battlefield" for c in (ring.id, signet.id))
    check(s)


def test_oko_the_ringleader_copies_each_other_nonland_permanent_but_not_himself(cards):
    s = build(cards, ["Oko, the Ringleader", "Grizzly Bears", "Sol Ring"], [])
    oko = put(s, "Oko, the Ringleader")
    put(s, "Grizzly Bears"), put(s, "Sol Ring")
    counter(s, oko, "loyalty", 5)
    act(s, "p1", type="activate_ability", card_id=oko.id, ability=ab(s, oko, "token_copy"))
    settle(s)
    assert sorted(chars(s, t).name for t in tokens(s)) == ["Grizzly Bears", "Sol Ring"]  # not Oko, not the Forests
    check(s)


# --- a plural name's "they / them" (The Notary Hobbits), "this token" in a granted ability (Jaxis) --------------------------------


def test_the_notary_hobbits_make_two_tokens_that_are_not_legendary_and_make_no_more(cards):
    s = build(cards, ["The Notary Hobbits"], [])
    hobbits = to_hand(s, "The Notary Hobbits")
    mana(s, G=2, C=3)
    act(s, "p1", type="cast_spell", card_id=hobbits.id)
    settle(s)
    toks = tokens(s, "The Notary Hobbits")
    assert len(toks) == 2 and all("Legendary" not in chars(s, t).supertypes for t in toks)  # 707.9b; a token's "if they're not a token" is false
    assert len([c for c in s.state.cards.values() if c.name == "The Notary Hobbits" and c.zone == "p1:battlefield" and not c.is_token]) == 1
    check(s)


def test_jaxis_token_copy_draws_when_it_dies_and_is_sacrificed_at_the_end_step(cards):
    s = build(cards, ["Jaxis, the Troublemaker", "Grizzly Bears"], [])
    jaxis, bears = put(s, "Jaxis, the Troublemaker"), put(s, "Grizzly Bears")
    seasoned(s, jaxis)
    mana(s, R=1)
    to_hand(s, "Forest")  # (the card to discard)
    act(s, "p1", type="activate_ability", card_id=jaxis.id, ability=ab(s, jaxis, "token_copy"), targets=[bears.id])
    settle(s)
    [tok] = tokens(s, "Grizzly Bears")
    assert "haste" in chars(s, tok).keywords and any("dies" in a.text for a in chars(s, tok).abilities)
    before = len([c for c in s.state.cards.values() if c.zone == "p1:hand"])
    stops(s, "end")
    to_phase(s, "end", turn=1)
    settle(s)
    assert not tokens(s) and len([c for c in s.state.cards.values() if c.zone == "p1:hand"]) == before + 1  # "When this token dies, draw a card."
    check(s)


def test_tilonallis_skinshifter_becomes_a_copy_of_the_other_attacker_until_end_of_turn(cards):
    s = build(cards, ["Tilonalli's Skinshifter", "Grizzly Bears"], [])
    shifter, bears = put(s, "Tilonalli's Skinshifter"), put(s, "Grizzly Bears")
    seasoned(s, shifter, bears)
    to_phase(s, "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": c.id, "target": "p2"} for c in (shifter, bears)])
    settle(s, prefer=[bears.id])
    c = chars(s, shifter)
    assert c.name == "Grizzly Bears" and c.pt == (2, 2)  # "it becomes a copy of another target nonlegendary attacking creature"
    assert s.state.cards[shifter.id].zone == "p1:battlefield"
    check(s)
    stops(s, "end")
    to_phase(s, "cleanup")
    assert chars(s, shifter).name == "Tilonalli's Skinshifter"
    check(s)
