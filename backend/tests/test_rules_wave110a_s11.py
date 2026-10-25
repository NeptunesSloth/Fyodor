"""Wave 110A session 11: real Oracle text cards (tests/fixtures/wave110a_cards.json), each scenario checks replay and save/load.

* Displaced Dinosaurs - 614.12 / 205.1b / 613.4b: a historic permanent you control becomes a 7/7 Dinosaur creature in addition as it enters.
* Zariel, Archduke of Avernus - -6 emblem: 511.2 / 500.8 untap a creature and get an additional combat phase after the first combat only.
* The Last Ronin's Technique - 702.190a sneak: the tokens enter tapped and attacking (508.4) only if the sneak cost was paid.
* Ezio Auditore da Firenze - 702.173a granted freerunning (Assassin spells you cast), and the combat damage trigger: pay {W}{U}{B}{R}{G} (the life
  test is on resolution) and the player loses the game.
"""

# ruff: noqa: F403, F405
from __future__ import annotations

from tests.wave110a_kit import *

DINO = "Displaced Dinosaurs"
ZARIEL = "Zariel, Archduke of Avernus"
RONIN = "The Last Ronin's Technique"
EZIO = "Ezio Auditore da Firenze"


@pytest.fixture()
def cards(settings):
    yield from open_repo(settings)


test_full = full_test([DINO, ZARIEL, RONIN, EZIO])


def test_historic_artifact_enters_as_a_7_7_dinosaur_creature(cards):
    s = build(cards, [DINO, "Sol Ring"])
    put(s, DINO)
    ring = cast(s, "Sol Ring")
    answer(s)
    c = ch(s, ring)
    assert {"Artifact", "Creature"} <= set(c.types) and "Dinosaur" in c.subtypes and c.pt == (7, 7)
    check(s)


def test_non_historic_permanent_is_unchanged(cards):
    s = build(cards, [DINO, "Grizzly Bears"])
    put(s, DINO)
    bears = cast(s, "Grizzly Bears")
    answer(s)
    assert ch(s, bears).pt == (2, 2) and "Dinosaur" not in ch(s, bears).subtypes  # 700.6: not historic
    check(s)


def test_opponents_historic_permanent_is_unchanged(cards):
    s = build(cards, ["Sol Ring"], [DINO])
    put(s, DINO, "p2")
    ring = cast(s, "Sol Ring")
    answer(s)
    assert "Creature" not in ch(s, ring).types  # "you control": the Dinosaurs' controller only
    check(s)


def _combats(s, bears, stop=60):
    """Attack with the bears in every combat of the turn until the end step; the number of declare attackers decisions seen."""
    seen = 0
    for _ in range(stop):
        d = s.state.rules.decision
        if d is None:
            if s.state.turn.phase == "end":
                return seen
            act(s, s.state.rules.priority, type="pass_priority")
        elif d.kind == "declare_attackers":
            seen += 1
            act(s, d.player, type="declare_attackers", attackers=[{"card_id": bears.id, "target": "p2"}] if not s.state.cards[bears.id].tapped else [])
        elif d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices)])
    raise AssertionError("never settled")


def test_zariel_emblem_untaps_a_creature_and_adds_one_combat_phase_only(cards):
    s = build(cards, [ZARIEL, "Grizzly Bears"])
    z = put(s, ZARIEL)
    bears = put(s, "Grizzly Bears")
    act(s, "p1", type="counter", card_ids=[z.id], kind="loyalty", delta=6)
    next_turn(s)
    stops(s)
    act(s, "p1", type="activate_ability", card_id=z.id, ability=2)
    answer(s)
    assert any(c.zone == "p1:command" for c in s.state.cards.values())
    to_phase(s, "declare_attackers")
    assert _combats(s, bears) == 2  # the first combat, then exactly one more: the added phase is not a "first combat phase"
    assert s.state.cards[bears.id].tapped  # it attacked in the second combat after the emblem untapped it
    check(s)


@pytest.mark.parametrize("sneak", [False, True])
def test_last_ronin_tokens_attack_only_when_sneaked(cards, sneak):
    from tests.test_rules_wave30i_sneak import attackers_declared, returned, sneak_of

    s = build(cards, [RONIN, "Grizzly Bears"], ["Llanowar Elves"])
    spell = to_hand(s, RONIN)
    if sneak:
        bear = put(s, "Grizzly Bears")
        s.state.rules.controlled_since[bear.id].turn = 0
        attackers_declared(s, [(bear, "p2")])
        mana(s, W=1, C=1)
        act(s, "p1", type="cast_spell", card_id=spell.id, alt_cost=sneak_of(s, cards, spell))
        returned(s, bear)
    else:
        mana(s, W=1, C=3)
        act(s, "p1", type="cast_spell", card_id=spell.id)
    answer(s)
    tokens = [c for c in s.state.cards.values() if c.is_token and c.zone == "p1:battlefield"]
    assert len(tokens) == 3 and all(t.tapped == sneak and (t.attacking is not None) == sneak for t in tokens)
    check(s)


def test_ezio_gives_assassin_spells_freerunning_after_an_assassin_hit_a_player(cards):
    from tests.test_rules_wave30i_sneak import sneak_of
    from tests.test_rules_wave43d_cast_keywords import connect

    s = build(cards, [EZIO, "Thorn of the Black Rose"])
    ezio = put(s, EZIO)
    s.state.rules.controlled_since[ezio.id].turn = 0
    thorn = to_hand(s, "Thorn of the Black Rose")
    mana(s, B=2)
    connect(s, ezio)
    mana(s, B=2)
    act(s, "p1", type="cast_spell", card_id=thorn.id, alt_cost=sneak_of(s, cards, thorn))  # {B}{B} instead of {3}{B}
    answer(s)
    assert s.state.cards[thorn.id].zone == "p1:battlefield"
    check(s)


def connect(s, ezio, pay=False):
    """Alice's next turn: Ezio attacks Bob unblocked; the "pay" decision of his trigger is answered yes."""
    until(s, lambda s: s.state.turn.number >= 3 and s.state.turn.phase == "main1" and s.state.rules.decision is None and s.state.turn.active_player == "p1")
    until(s, lambda s: s.state.rules.decision is not None and s.state.rules.decision.kind == "declare_attackers")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": ezio.id, "target": "p2"}])
    for _ in range(60):
        d = s.state.rules.decision
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        elif d is not None:
            act(s, d.player, type="choose", decision_id=d.id, option_ids=["pay"] if d.kind == "choose_one" and pay else [o.id for o in d.options][: max(1, d.min_choices)])
        elif s.state.rules.winner is not None or (s.state.turn.phase == "main2" and not s.state.zones.get("stack")):
            return
        else:
            act(s, s.state.rules.priority, type="pass_priority")


def life_of(s):
    return s.state.players["p2"].life


@pytest.mark.parametrize("life, loses", [(10, True), (11, False)])
def test_ezio_pays_five_colors_to_make_a_player_at_ten_or_less_life_lose(cards, life, loses):
    s = build(cards, [EZIO, "Plains", "Island", "Swamp", "Mountain", "Forest"])
    for land in ("Plains", "Island", "Swamp", "Mountain", "Forest"):
        put(s, land)
    ezio = put(s, EZIO)
    s.state.rules.controlled_since[ezio.id].turn = 0
    act(s, "p1", type="set_life", player="p2", value=life + 3)  # Ezio deals 3 combat damage
    connect(s, ezio, pay=True)
    assert ("p2" in s.state.rules.lost) == loses and (loses or life_of(s) == life)  # 104.3e;   # the life test is made on resolution
    check(s)
