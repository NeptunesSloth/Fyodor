"""-- planechase more 4 (wave G2) -- Deceptive Divination and Happy Yargle Day! (app/rules/planar_more4.py), Ood Sphere's tap restriction against an
effect's tap (Oubliette), and suspend / foretell / Talon Gates as special actions the auto-pass counts, on real Oracle text with the rules engine
on, then ``check`` (replay + save/load round trip)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.cards.importer import build_database
from app.config import Settings
from app.game.factory import PlayerSetup, new_game
from app.game.session import GameSession
from app.game.state import GameSettings, PlanarCard
from app.rules import coverage
from app.rules.plan import Plan
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act, deck, enable
from tests.test_planechase import script
from tests.test_rules_conditionals import to_turn
from tests.test_rules_wave12a_counters_keywords import real
from tests.wave9c_kit import check, mana

# Oracle text exactly as in the card database (data/cards.sqlite)
PLANES = {
    'Deceptive Divination': ('Plane — Secret Lair', 'Change the text of each sorcery spell and sorcery card not on the stack by replacing "sorcery" with "instant."\nWhenever chaos ensues, choose two target players. Each of them searches their library for a card, then shuffles and puts that card on top.'),  # noqa: E501
    'Happy Yargle Day!': ('Plane — Secret Lair', "At the beginning of each player's end step, if that player doesn't control a creature named Yargle, Glutton of Urborg, that player puts a bargle counter on a creature they control. It becomes a copy of Yargle, Glutton of Urborg, except it isn't legendary.\nWhenever chaos ensues, choose Swords to Plowshares, Opt, Fatal Push, Anger of the Gods, or Explore at random. Copy the chosen card. You may cast the copy without paying its mana cost."),  # noqa: E501
    'Ood Sphere': ('Plane — Horsehead Nebula', "Song of the Ood — Noncreature spells have convoke. (A player's creatures can help cast those spells. Each creature they tap while casting a noncreature spell pays for {1} or one mana of that creature's color.)\nRed-Eye — Whenever chaos ensues, for each opponent, goad up to one target creature that opponent controls. Until your next turn, those creatures can't become tapped unless they're being declared as attackers."),  # noqa: E501
    'Talon Gates': ('Plane — Dominaria', "Any time you could cast a sorcery, you may exile a nonland card from your hand with X time counters on it, where X is its mana value. If the exiled card doesn't have suspend, it gains suspend. (At the beginning of its owner's upkeep, they remove a time counter. When the last is removed, the player may cast it without paying its mana cost. If it's a creature, it has haste.)\nWhenever chaos ensues, remove two time counters from each suspended card you own."),  # noqa: E501
    'Event Horizon': ('Plane — Blind Eternities', 'Nonbasic lands are Wastes.\nWhenever you tap a permanent for {C}, add an additional {C}.\nWhenever chaos ensues, choose one —\n• Draw four cards.\n• Destroy target permanent.\n• You may return target creature card from your graveyard to the battlefield.'),  # noqa: E501
    'Academy at Tolaria West':('Plane — Dominaria', 'At the beginning of your end step, if you have no cards in hand, draw seven cards.\nWhenever chaos ensues, discard your hand.'),  # noqa: E501
}
FILLER = "Academy at Tolaria West"
YARGLE = "Yargle, Glutton of Urborg"
EXTRA = [card(n, set_code="opca", number=f"PG2-{i}", layout="planar", type_line=t, oracle_text=o) for i, (n, (t, o)) in enumerate(PLANES.items())]
EXTRA += [real("Runeclaw Bear", "{1}{G}", 2, "Creature — Bear", "", ("2", "2"), "G"),
          real("Elvish Mystic", "{G}", 1, "Creature — Elf Druid", "{T}: Add {G}.", ("1", "1"), "G"),
          real(YARGLE, "{4}{B}", 5, "Legendary Creature — Frog Spirit", "", ("9", "3"), "B"),
          real("Divination", "{2}{U}", 3, "Sorcery", "Draw two cards.", None, "U"),
          real("Fatal Push", "{B}", 1, "Instant", "Destroy target creature if it has mana value 2 or less.\nRevolt — Destroy that creature if it has "
               "mana value 4 or less instead if a permanent left the battlefield under your control this turn.", None, "B"),
          real("Anger of the Gods", "{1}{R}{R}", 3, "Sorcery", "Anger of the Gods deals 3 damage to each creature. If a creature dealt damage this way "
               "would die this turn, exile it instead.", None, "R"),
          real("Explore", "{1}{G}", 2, "Sorcery", "You may play an additional land this turn.\nDraw a card.", None, "G"),
          real("Oubliette", "{1}{B}{B}", 3, "Enchantment", "When this enchantment enters, target creature phases out until this enchantment leaves the "
               "battlefield. Tap that creature as it phases in this way. (Auras and Equipment phase out with it. While permanents are phased out, "
               "they're treated as though they don't exist.)", None, "B"),
          real("Ancestral Vision", "", 0, "Sorcery", "Suspend 4—{U} (Rather than cast this card from your hand, pay {U} and exile it with four time "
               "counters on it. At the beginning of your upkeep, remove a time counter. When the last is removed, you may cast it without paying its "
               "mana cost.)\nTarget player draws three cards.", None, "U")]


@pytest.fixture()
def card_db(settings: Settings) -> Path:
    settings.ensure_dirs()
    build_database([*fixture_cards(), *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    return settings.cards_db_path


class _InOrder:
    def shuffle(self, items: list) -> None:
        pass

    def randint(self, lo: int, hi: int) -> int:
        return lo


def table(cards, planes: list[str]) -> GameSession:
    alice = deck(cards, "Krenko, Mob Boss", [(3, "Runeclaw Bear"), (1, "Divination"), (1, "Anger of the Gods"), (1, "Opt"), (1, "Oubliette"),
                                             (1, "Ancestral Vision"), (9, "Forest")])
    bob = deck(cards, "Atraxa, Praetors' Voice", [(2, "Runeclaw Bear"), (1, "Elvish Mystic"), (1, "Opt"), (10, "Island")])
    pool = [PlanarCard(printing_id=cards.resolve(n)["id"], name=n, phenomenon=False) for n in planes]
    state = new_game([PlayerSetup("Alice", cards=alice), PlayerSetup("Bob", cards=bob)], shuffle=False, first_player=0,
                     settings=GameSettings(planechase=True, planar_deck_size=len(pool)), planar_pool=lambda: pool, rng=_InOrder())
    enable(state)
    s = GameSession(state, cards=cards)
    act(s, "p1", type="pass_priority")  # → Alice's main phase
    return s


def resolve(s, picks=()):
    for _ in range(80):
        d = s.state.rules.decision
        if d is not None and d.kind in ("declare_attackers", "declare_blockers"):
            return
        if d is not None:
            chosen = [o.id for p in picks for o in d.options if p in (o.id, o.card_id, o.label)][: d.max_choices]
            if len(chosen) < d.min_choices:
                chosen = [o.id for o in d.options][: d.min_choices]
            act(s, d.player, type="choose", decision_id=d.id, option_ids=chosen)
        elif s.state.zones.get("stack"):
            act(s, s.state.rules.priority, type="pass_priority")
        else:
            return
    raise AssertionError("never settled")


def roll(s, monkeypatch, values, picks=()):
    """Alice rolls the planar die: the server's numbers in order (the d6 first: 1 planeswalker, 2 chaos, 3-6 blank)."""
    from app.game.handlers.planechase import roll_cost

    if cost := roll_cost(s.state):
        mana(s, C=cost)
    script(monkeypatch, list(values))
    act(s, "p1", type="roll_planar_die")
    resolve(s, picks)


def place(s, name, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith((":battlefield", ":command")))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": "battlefield"})
    return c


def to_zone(s, name, zone, pid="p1"):
    c = next(c for c in s.state.cards.values() if c.name == name and c.owner == pid and not c.zone.endswith((f":{zone}", ":command")))
    act(s, pid, type="move", card_ids=[c.id], to={"player": pid, "zone": zone})
    return c


def plan(s, pid="p1"):
    return Plan(s.state, pid, s.cards, None)


def stats(s, c):
    from app.rules import sba

    card_ = s.state.cards[c.id]
    ch = plan(s).ch(card_)
    return sba.power(card_, ch), sba.toughness(card_, ch)


@pytest.mark.parametrize("name", ["Deceptive Divination", "Happy Yargle Day!"])
def test_full(cards, name):
    assert coverage.of_card_data(cards.resolve(name)).level == "FULL"


# -- Deceptive Divination: "sorcery" becomes "instant" on every sorcery card and spell (612.1-2, 613.1c) -----------------------------------
@pytest.mark.parametrize("plane", ["Deceptive Divination", FILLER])
def test_deceptive_divination_sorcery_cards_are_instants_in_every_zone(cards, plane):
    from app.game.views import card_view

    s = table(cards, [plane, "Talon Gates"])
    div = to_zone(s, "Divination", "hand")
    anger = next(c for c in s.state.cards.values() if c.name == "Anger of the Gods" and c.owner == "p1")  # (in her library)
    vision = to_zone(s, "Ancestral Vision", "graveyard")
    up = plane == "Deceptive Divination"
    for c in (div, anger, vision):
        types = plan(s).ch(s.state.cards[c.id]).types
        assert ("Instant" in types and "Sorcery" not in types) if up else ("Sorcery" in types and "Instant" not in types)
    bear = next(c for c in s.state.cards.values() if c.name == "Runeclaw Bear" and c.owner == "p1")
    assert plan(s).ch(bear).types == frozenset({"Creature"})  # (only sorceries)
    view = card_view(s.state, s.state.cards[div.id], "p2")  # (a hidden card: its view never carries characteristics)
    assert view.get("hidden") and "card_id" not in view and "name" not in view
    # 307.1 / 304.5: a sorcery is cast only in your main phase with the stack empty; an instant any time you have priority
    from app.rules import casting

    to_turn(s, 2)  # Bob's main phase: Bob has priority
    mana(s, "p1", U=1, C=2)
    assert casting.castable(s.state, "p1", s.state.cards[div.id], s.cards, check_priority=False) is up
    assert casting.has_responses(s.state, "p1", s.cards) is up  # (the auto-pass stops for her only when she can cast it)
    if not up:
        return
    bobs = to_zone(s, "Opt", "hand", "p2")
    mana(s, "p2", U=1)
    act(s, "p2", type="cast_spell", card_id=bobs.id, sources=[])  # (with a spell on the stack, the auto-pass asks has_responses)
    if s.state.rules.priority == "p2":
        act(s, "p2", type="pass_priority")
    assert s.state.rules.priority == "p1" and s.state.zones.get("stack")
    hand = len(s.state.zones["p1:hand"])
    act(s, "p1", type="cast_spell", card_id=div.id, sources=[])  # (in Bob's turn, in response)
    resolve(s)
    assert s.state.cards[div.id].zone == "p1:graveyard" and len(s.state.zones["p1:hand"]) == hand - 1 + 2
    check(s)


def test_deceptive_divination_changes_the_word_in_rules_text_but_not_names():
    from app.rules import planar_more4

    assert planar_more4.retext("Exile target card that's an instant or sorcery from your graveyard.", ("Mizzix's Mastery",)) \
        == "Exile target card that's an instant or instant from your graveyard."
    assert planar_more4.retext("Activate only as a sorcery.", ()) == "Activate only as an instant."
    named = planar_more4.retext("Search for a card named Sorcery Hunter, then cast sorceries.", ("X",),
                                lambda text, at: "Sorcery Hunter" if text.startswith("Sorcery Hunter", at) else None)
    assert named == "Search for a card named Sorcery Hunter, then cast instants."


def test_deceptive_divination_chaos_two_target_players_each_tutor_to_the_top(cards, monkeypatch):
    s = table(cards, ["Deceptive Divination", FILLER])
    roll(s, monkeypatch, [2], picks=["p1", "p2", "Divination", "Opt"])  # (the targets: both players; each searches privately)
    top1 = s.state.cards[s.state.zones["p1:library"][0]]
    top2 = s.state.cards[s.state.zones["p2:library"][0]]
    assert top1.name == "Divination" and top2.name == "Opt"
    check(s)


# -- Happy Yargle Day! -------------------------------------------------------------------------------------------------------------------
def test_happy_yargle_day_each_end_step_a_creature_becomes_a_nonlegendary_yargle(cards):
    s = table(cards, ["Happy Yargle Day!", FILLER])
    bear = place(s, "Runeclaw Bear")
    bobs = place(s, "Runeclaw Bear", "p2")
    to_turn(s, 2)  # Alice's end step: her bear gets a bargle counter and becomes Yargle
    ch = plan(s).ch(s.state.cards[bear.id])
    assert ch.name == YARGLE and "Legendary" not in ch.supertypes and ch.subtypes == frozenset({"Frog", "Spirit"})
    assert stats(s, bear) == (9, 3) and s.state.cards[bear.id].counters.get("bargle") == 1
    assert plan(s).ch(s.state.cards[bobs.id]).name == "Runeclaw Bear"
    to_turn(s, 3)  # Bob's end step: each player's — his bear too
    assert plan(s).ch(s.state.cards[bobs.id]).name == YARGLE
    second = place(s, "Runeclaw Bear")
    to_turn(s, 4)  # Alice controls a creature named Yargle: nothing (603.4)
    assert plan(s).ch(s.state.cards[second.id]).name == "Runeclaw Bear" and not s.state.cards[second.id].counters.get("bargle")
    act(s, s.state.turn.active_player, type="planeswalk")  # 611.2a: the copy effect has no duration — it stays after the plane leaves
    assert plan(s).ch(s.state.cards[bear.id]).name == YARGLE
    check(s)


@pytest.mark.parametrize("pick,name", [(1, "Opt"), (2, "Fatal Push")])
def test_happy_yargle_day_chaos_copies_a_random_card_and_casts_it_free(cards, monkeypatch, pick, name):
    s = table(cards, ["Happy Yargle Day!", FILLER])
    bobs = place(s, "Runeclaw Bear", "p2")
    hand = len(s.state.zones.get("p1:hand", []))
    roll(s, monkeypatch, [2, pick], picks=[name, bobs.id])  # (the die: chaos; the random pick: the server's number)
    assert any(name in str(e) for e in s.state.log[-40:])  # (the pick is logged)
    if name == "Opt":
        assert len(s.state.zones.get("p1:hand", [])) == hand + 1
    else:
        assert s.state.cards[bobs.id].zone == "p2:graveyard"
    assert not [c for c in s.state.cards.values() if c.name == name and c.is_token and c.zone != "stack"]  # (the copy is gone, 704.5e)
    check(s)


def test_happy_yargle_day_chaos_copy_may_be_declined(cards, monkeypatch):
    s = table(cards, ["Happy Yargle Day!", FILLER])
    hand = len(s.state.zones.get("p1:hand", []))
    roll(s, monkeypatch, [2, 1])  # (Opt; nothing picked: not cast)
    assert len(s.state.zones.get("p1:hand", [])) == hand
    check(s)


# -- Ood Sphere: an effect's tap (Oubliette's, as the creature phases in) leaves a held creature untapped, it doesn't fail ------------------
def test_ood_sphere_oubliette_phase_in_tap_is_skipped_not_refused(cards, monkeypatch):
    s = table(cards, ["Ood Sphere", FILLER])
    elf = place(s, "Elvish Mystic", "p2")
    roll(s, monkeypatch, [2], picks=[elf.id])  # Red-Eye: goaded, can't become tapped until Alice's next turn
    assert s.state.rules.planar_more3_f2.get("ood")
    oub = to_zone(s, "Oubliette", "hand")
    mana(s, B=2, C=1)
    act(s, "p1", type="cast_spell", card_id=oub.id, sources=[])
    resolve(s, picks=[elf.id])  # its enters trigger: the elf phases out until Oubliette leaves
    assert s.state.cards[elf.id].zone == "p2:phased"
    act(s, "p1", type="move", card_ids=[oub.id], to={"player": "p1", "zone": "graveyard"})  # (it phases in; "tap that creature" can't)
    act(s, "p1", type="pass_priority")
    resolve(s)
    assert s.state.cards[elf.id].zone == "p2:battlefield" and not s.state.cards[elf.id].tapped
    check(s)


# -- suspend / Talon Gates: special actions the auto-pass counts (116.2f, 702.62a; Talon Gates ruling 2012-06-01) ---------------------------
def test_special_actions_count_suspend_and_talon_gates(cards):
    from app.rules import casting

    s = table(cards, [FILLER, "Talon Gates"])
    vision = to_zone(s, "Ancestral Vision", "hand")
    assert not casting.special_action(s.state, "p1", s.cards)  # (no {U})
    mana(s, U=1)
    assert casting.special_action(s.state, "p1", s.cards)  # Suspend 4—{U}: in her main phase with the stack empty
    act(s, "p1", type="move", card_ids=[vision.id], to={"player": "p1", "zone": "library"})
    to_zone(s, "Runeclaw Bear", "hand")
    assert not casting.special_action(s.state, "p1", s.cards)  # (a creature card in hand, no Talon Gates face up)
    act(s, "p1", type="planeswalk")  # → Talon Gates
    assert casting.special_action(s.state, "p1", s.cards)  # any time she could cast a sorcery: exile a nonland card from her hand
    assert not casting.special_action(s.state, "p1", s.cards, instant=True)  # (not a response)
    assert not casting.special_action(s.state, "p2", s.cards)  # (Bob: not his main phase)
    check(s)


# -- modal abilities: a mode that opens "You may …" (608.2d: chosen as it resolves; the grammar change of wave G2) -------------------------------
# (Event Horizon stays refused for "Nonbasic lands are Wastes." — docs/research/planechase-refused.md; its chaos ability is read now)
MAY_MODE = "You may return target creature card from your graveyard to the battlefield."


def test_modal_you_may_mode_reads_as_the_modes_own_choice(cards):
    from app.rules import characteristics as chars
    from app.rules import scripts

    defs = scripts.definitions(chars.printed_from_data(cards.resolve("Event Horizon"), 0))
    modal = next(d for d in defs.values() if d.get("modes"))
    mode = next(m for m in modal["modes"] if m["text"].startswith("• You may") or m["text"].startswith("You may"))
    assert mode["effects"][0] == {"do": "may_rest", "skip": len(mode["effects"]) - 1} and not modal.get("optional")


@pytest.mark.parametrize("answer", ["yes", "no"])
def test_modal_you_may_mode_is_asked_as_it_resolves(cards, monkeypatch, answer):
    s = table(cards, ["Event Horizon", FILLER])
    bear = to_zone(s, "Runeclaw Bear", "graveyard")
    roll(s, monkeypatch, [2], picks=[MAY_MODE, f"• {MAY_MODE}", bear.id, answer])
    assert s.state.cards[bear.id].zone == ("p1:battlefield" if answer == "yes" else "p1:graveyard")
    check(s)
