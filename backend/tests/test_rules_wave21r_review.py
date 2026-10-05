"""Wave 21 review: scenarios the builders didn't play (real Oracle text from tests/fixtures/wave21r_cards.json, data/cards.sqlite).

Every scenario checks that replaying the recorded history reproduces the table and that a save/load round trip keeps it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_rules_conditionals import until
from tests.test_rules_wave5j_token_copies import ch, drive, find, game, mana, put, roundtrip, token

DATA = json.loads((Path(__file__).parent / "fixtures" / "wave21r_cards.json").read_text("utf-8"))
EXTRA = [card(c["name"], set_code="t21r", number=f"R{i:03d}", **{k: v for k, v in c.items() if k != "name"}) for i, c in enumerate(DATA)]
BOLT = card("Probe Bolt", set_code="t21r", number="R900", mana_cost="{R}", cmc=1.0, type_line="Instant", oracle_text="Probe Bolt deals 1 damage to any target.",
            colors=["R"], color_identity=["R"])
SPIRIT = card("Probe Spirit", set_code="t21r", number="R901", mana_cost="{1}", cmc=1.0, type_line="Creature — Spirit", oracle_text="",
              power="1", toughness="1")
X_HORROR = card("Probe X Horror", set_code="t21r", number="R902", mana_cost="{X}{B}", cmc=1.0, type_line="Creature — Horror", oracle_text="",
                power="1", toughness="1", colors=["B"], color_identity=["B"])


@pytest.fixture()
def card_db(settings):
    from app.cards.importer import build_database

    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA, BOLT, SPIRIT, X_HORROR], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


def unready(s, *cs):
    for c in cs:
        s.state.rules.controlled_since[c.id].turn = 0


def power(s, c):
    from app.rules import sba

    return sba.power(s.state.cards[c.id], ch(s, c))


def life(s, pid):
    return s.state.players[pid].life


def three(cards, alice=(), bob=(), carol=()):
    decks = [deck(cards, "Krenko, Mob Boss", [*((1, n) for n in alice), (20, "Forest")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in bob), (20, "Island")]),
             deck(cards, "Atraxa, Praetors' Voice", [*((1, n) for n in carol), (20, "Island")])]
    s = GameSession(enable(new_game([PlayerSetup(n, cards=d) for n, d in zip(("Alice", "Bob", "Carol"), decks, strict=True)], shuffle=False)),
                    cards=cards)
    act(s, "p1", type="pass_priority")
    return s


def to_attack(s):
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")


def battlefield(s, pid="p1"):
    return [s.state.cards[c].name for c in s.state.zones[f"{pid}:battlefield"]]


@pytest.mark.parametrize(("target", "treasures"), [("p2", 0), ("p3", 2)])
def test_alliance_background_judges_the_attacked_player_against_every_opponent(cards, target, treasures):
    s = three(cards, ["Guild Artisan"])
    put(s, "Guild Artisan")
    krenko = put(s, "Krenko, Mob Boss")
    unready(s, krenko)
    act(s, "p2", type="set_life", player="p2", value=30)
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": krenko.id, "target": target}])
    drive(s)
    assert sum(1 for c in s.state.cards.values() if c.is_token and c.name == "Treasure") == treasures
    roundtrip(s)


def picker(*labels):
    """Answer decisions by the first option whose label contains one of ``labels`` (in turn), else the first options."""
    todo = list(labels)

    def choose(d):
        print("DECISION", d.kind, d.prompt, [(o.id, o.label) for o in d.options])
        if todo:
            want = todo.pop(0)
            if isinstance(want, list):
                return want
            hit = [o.id for o in d.options if want.lower() in (o.label or "").lower()]
            assert hit, (want, [o.label for o in d.options])
            return hit[:1]
        return None
    return choose


def test_hikari_blinks_and_returns_at_the_next_end_step(cards):
    s = game(cards, ["Hikari, Twilight Guardian", "Probe Spirit"])
    hikari = put(s, "Hikari, Twilight Guardian")
    from tests.test_rules_wave5j_token_copies import cast
    cast(s, "Probe Spirit", C=1)
    drive(s, picker("pay"))
    assert s.state.cards[hikari.id].zone == "p1:exile"
    until(s, lambda s: s.state.turn.number == 2)
    assert s.state.cards[hikari.id].zone == "p1:battlefield"  # (the card the payment exiled: a new object, 400.7)
    roundtrip(s)


def test_attack_in_the_box_pumps_and_is_sacrificed(cards):
    s = game(cards, ["Attack-in-the-Box"])
    box = put(s, "Attack-in-the-Box")
    unready(s, box)
    to_attack(s)
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": box.id, "target": "p2"}])
    drive(s, picker("yes"))
    assert ch(s, box).power is not None
    until(s, lambda s: s.state.turn.phase == "main2")
    assert life(s, "p2") == 40 - 6  # (a 2/4 with +4/+0)
    until(s, lambda s: s.state.turn.number == 2)
    assert s.state.cards[box.id].zone == "p1:graveyard"
    roundtrip(s)



def test_necrodominance_pays_any_amount_of_life_and_draws_that_many(cards):
    s = game(cards, ["Necrodominance"])
    put(s, "Necrodominance")
    hand = len(s.state.zones["p1:hand"])
    until(s, lambda s: s.state.turn.phase == "end" and s.state.rules.decision is not None)
    drive(s, picker(["x:3"]))
    assert life(s, "p1") == 37 and len(s.state.zones["p1:hand"]) == hand + 3
    roundtrip(s)


def test_malfegor_edicts_once_per_card_discarded(cards):
    s = game(cards, ["Malfegor", "Probe Spirit", "Probe Bolt"])
    put(s, "Probe Spirit", "hand")
    put(s, "Probe Bolt", "hand")
    hand = len(s.state.zones["p1:hand"])
    for i in range(hand + 1):
        token(s, "p2", f"Wolf {i}", "2/2", "Token Creature — Wolf")
    malfegor = put(s, "Malfegor", "hand")
    mana(s, B=2, R=2, C=2)
    act(s, "p1", type="cast_spell", card_id=malfegor.id)
    drive(s)
    assert len([c for c in s.state.zones["p2:battlefield"] if s.state.cards[c].is_token]) == 1
    roundtrip(s)


def test_mind_maggots_discards_only_creature_cards(cards):
    s = game(cards, ["Mind Maggots", "Probe Spirit", "Probe Bolt"])
    spirit = put(s, "Probe Spirit", "hand")
    bolt = put(s, "Probe Bolt", "hand")
    maggots = put(s, "Mind Maggots", "hand")
    mana(s, B=1, C=3)
    act(s, "p1", type="cast_spell", card_id=maggots.id)
    drive(s, picker([spirit.id]))
    assert s.state.cards[spirit.id].zone == "p1:graveyard" and s.state.cards[bolt.id].zone == "p1:hand"
    assert ch(s, maggots).power is not None
    roundtrip(s)


def test_fable_chapter_two_discards_up_to_two_and_draws_that_many(cards):
    s = game(cards, ["Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "Probe Spirit", "Probe Bolt"])
    fable = put(s, "Fable of the Mirror-Breaker // Reflection of Kiki-Jiki", "hand")
    mana(s, R=1, C=2)
    act(s, "p1", type="cast_spell", card_id=fable.id)
    drive(s)  # (chapter I: a Goblin Shaman)
    spirit, bolt = put(s, "Probe Spirit", "hand"), put(s, "Probe Bolt", "hand")
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None)
    hand = len(s.state.zones["p1:hand"])
    drive(s, picker([spirit.id, bolt.id]))
    assert s.state.cards[spirit.id].zone == s.state.cards[bolt.id].zone == "p1:graveyard"
    assert len(s.state.zones["p1:hand"]) == hand
    roundtrip(s)


@pytest.mark.parametrize("other", [False, True])
def test_lord_of_the_pit_sacrifices_another_creature_or_deals_7(cards, other):
    s = game(cards, ["Lord of the Pit"])
    lord = put(s, "Lord of the Pit")
    if other:
        token(s, "p1", "Thrull", "1/1", "Token Creature — Thrull")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[lord.id].zone == "p1:battlefield"
    assert life(s, "p1") == (40 if other else 33)
    roundtrip(s)


def test_crackling_drake_counts_face_up_instants_in_exile_and_the_graveyard_only(cards):
    s = game(cards, ["Crackling Drake", "Probe Bolt"], ["Probe Bolt"])
    drake = put(s, "Crackling Drake")
    bolt = put(s, "Probe Bolt", "hand")
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "exile"}, face_down=True)
    assert power(s, drake) == 0  # (406.3a: a card exiled face down has no characteristics)
    act(s, "p1", type="move", card_ids=[bolt.id], to={"player": "p1", "zone": "graveyard"})
    theirs = find(s, "Probe Bolt", "p2")
    act(s, "p2", type="move", card_ids=[theirs.id], to={"player": "p2", "zone": "exile"})
    assert power(s, drake) == 1  # (Bob's card: not one Alice owns)
    roundtrip(s)


def test_cellarspawn_counts_x_in_the_mana_value_of_an_x_spell(cards):
    s = game(cards, ["Ancient Cellarspawn", "Probe X Horror"])
    put(s, "Ancient Cellarspawn")
    horror = put(s, "Probe X Horror", "hand")
    mana(s, B=1, C=2)  # X = 3: a mana value of 4 on the stack (202.3e), and {1} less to pay: 3 spent
    act(s, "p1", type="cast_spell", card_id=horror.id, x_value=3)
    drive(s, picker("Bob"))
    assert life(s, "p2") == 40 - 1
    roundtrip(s)


def test_alluring_siren_forces_an_attack_on_its_controller_in_the_declaration(cards):
    from app.game.errors import ActionError

    s = three(cards, ["Alluring Siren"], ["Scuttlemutt"])
    siren = put(s, "Alluring Siren")
    victim = put(s, "Scuttlemutt", pid="p2")
    unready(s, siren, victim)
    act(s, "p1", type="set_stops", others=["begin_combat"])
    until(s, lambda s: s.state.turn.number == 2 and s.state.turn.phase == "begin_combat" and s.state.rules.priority == "p1"
          and s.state.rules.decision is None)
    i = next(a.index for a in ch(s, siren).abilities if a.kind == "activated")
    act(s, "p1", type="activate_ability", card_id=siren.id, ability=i, targets=[victim.id])
    drive(s)
    to_attack(s)
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[])
    with pytest.raises(ActionError):
        act(s, "p2", type="declare_attackers", attackers=[{"card_id": victim.id, "target": "p3"}])
    act(s, "p2", type="declare_attackers", attackers=[{"card_id": victim.id, "target": "p1"}])
    roundtrip(s)


def test_hawkeye_the_entering_hero_deals_the_damage(cards):
    s = game(cards, ["Hawkeye, Trick Shot", "Zarda, the Power Princess"])
    hawkeye = put(s, "Hawkeye, Trick Shot", "hand")
    mana(s, R=1, C=3)
    act(s, "p1", type="cast_spell", card_id=hawkeye.id)
    drive(s, picker("Bob"))
    assert life(s, "p2") == 39  # (one Hero)
    zarda = put(s, "Zarda, the Power Princess", "hand")  # (the entering Hero is the source: "src": "event")
    mana(s, W=1, C=3)
    act(s, "p1", type="cast_spell", card_id=zarda.id)
    drive(s, picker("Bob"))
    assert life(s, "p2") == 37  # (two Heroes; Zarda, the entering Hero, is the source)
    roundtrip(s)


def test_vincent_valentine_grows_by_the_dead_creatures_last_power(cards):
    s = game(cards, ["Vincent Valentine // Galian Beast", "Probe Bolt"])
    vincent = put(s, "Vincent Valentine // Galian Beast")
    wolf = token(s, "p2", "Wolf", "1/1", "Token Creature — Wolf")
    act(s, "p2", type="counter", card_ids=[wolf.id], kind="+1/+1", delta=2)
    act(s, "p2", type="set_damage", card_ids=[wolf.id], value=2)
    bolt = put(s, "Probe Bolt", "hand")
    mana(s, R=1)
    act(s, "p1", type="cast_spell", card_id=bolt.id, targets=[wolf.id])
    drive(s)
    assert s.state.cards[vincent.id].counters.get("+1/+1") == 3
    roundtrip(s)


def test_spiritual_sanctuary_each_player_with_a_plains_gains_in_their_upkeep(cards):
    s = game(cards, ["Spiritual Sanctuary"])
    put(s, "Spiritual Sanctuary")
    token(s, "p2", "Plains", None, "Token Land — Plains")
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert life(s, "p2") == 41 and life(s, "p1") == 40  # (Alice has no Plains)
    roundtrip(s)


def test_raffines_guidance_is_cast_from_the_graveyard_for_its_alternative_cost(cards):
    s = game(cards, ["Raffine's Guidance", "Grizzly Bears"])
    bears = put(s, "Grizzly Bears")
    aura = put(s, "Raffine's Guidance", "graveyard")
    mana(s, W=1, C=2)
    i = next(a.index for a in ch(s, aura).abilities if "graveyard" in a.text)
    act(s, "p1", type="cast_spell", card_id=aura.id, alt_cost=f"{aura.id}:{i}", targets=[bears.id])
    drive(s)
    assert s.state.cards[aura.id].attached_to == bears.id and power(s, bears) == 3
    assert not s.state.players["p1"].mana.get("C")
    roundtrip(s)


def test_estrids_invocation_copy_blinks_itself_in_the_upkeep(cards):
    s = game(cards, ["Estrid's Invocation", "Spiritual Sanctuary"])
    put(s, "Spiritual Sanctuary")
    inv = put(s, "Estrid's Invocation", "hand")
    mana(s, U=1, C=2)
    act(s, "p1", type="cast_spell", card_id=inv.id)
    drive(s, picker("Spiritual"))
    assert ch(s, inv).name == "Spiritual Sanctuary"
    until(s, lambda s: s.state.turn.number == 3 and s.state.rules.decision is not None)
    drive(s, picker("pay", "Spiritual"))
    until(s, lambda s: s.state.turn.number == 3 and s.state.turn.phase == "main1")
    assert s.state.cards[inv.id].zone == "p1:battlefield"
    roundtrip(s)
