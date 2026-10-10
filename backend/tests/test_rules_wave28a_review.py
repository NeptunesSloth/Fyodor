"""Review of wave 28A (play a card as an effect resolves; CR 2026-09-25). Real Oracle text; replay and a save and a load.

* 709.3a / 601.3e: a split card is cast as one half and only that half is evaluated: "cast a sorcery spell" (Aisha of Sparks and Smoke)
  never casts the instant half of Consecrate // Consume, and Consume's own mana value (4) is the one compared with the damage.
* A free cast the engine granted takes the face its own choice named, never one sent with the cast (a transformed Delver, 712.11a).
* 305.2a-b: "You may play lands and cast spells from among cards exiled this way" (Gix) plays only as many lands as the player has land plays
  left, one at a time, a spell between them, with a pause for a shock land's choice (614.12a) that survives a save and a load.
* 800.4a: a player who leaves while another chooses among their exiled cards takes those cards out of the game: the choice is asked again.
* 107.3b: X is 0 for a spell cast without paying its mana cost (Djinn of Wishes revealing Blaze).
"""

from __future__ import annotations

import pytest

from app.game.errors import ActionError
from tests.fixtures.cards import card, fixture_cards
from tests.game_helpers import act
from tests.test_rules_effects import pass_until_stack_empty, replay_matches
from tests.test_rules_wave28a_play_now import REAL, _face
from tests.wave9c_kit import build, card_named, mana, put, reloaded

EXTRA = [
    card("Exploration", set_code="r28a", number="1", mana_cost="{G}", cmc=1.0, type_line="Enchantment", colors=["G"], color_identity=["G"],
         oracle_text="You may play an additional land on each of your turns."),
    card("Blaze", set_code="r28a", number="2", mana_cost="{X}{R}", cmc=1.0, type_line="Sorcery", colors=["R"], color_identity=["R"],
         oracle_text="Blaze deals X damage to any target."),
    card("Consecrate // Consume", set_code="r28a", number="3", layout="split", mana_cost="{1}{W/B} // {2}{W}{B}", cmc=6.0,
         type_line="Instant // Sorcery", colors=["W", "B"], color_identity=["W", "B"],
         card_faces=[_face("Consecrate", "{1}{W/B}", "Instant", "Exile target card from a graveyard.\nDraw a card."),
                     _face("Consume", "{2}{W}{B}", "Sorcery", "Target player sacrifices a creature with the greatest power among creatures they "
                           "control. You gain life equal to its power.")]),
    card("Aisha of Sparks and Smoke", set_code="r28a", number="4", mana_cost="{1}{R}{R}", cmc=3.0, type_line="Legendary Creature — Human Warrior",
         colors=["R"], color_identity=["R"], power="4", toughness="2", keywords=["Prowess"],
         oracle_text="Prowess (Whenever you cast a noncreature spell, this creature gets +1/+1 until end of turn.)\n{R/W}: Aisha of Sparks and Smoke "
         "gains first strike until end of turn.\nWhenever Aisha deals combat damage, you may cast a sorcery spell from your hand with mana value less "
         "than or equal to that damage without paying its mana cost."),
]
NAMES = [c["name"] for c in REAL + EXTRA]


@pytest.fixture()
def cards(settings):
    from app.cards.images import ImageStore
    from app.cards.importer import build_database
    from app.cards.repository import CardRepository

    settings.ensure_dirs()
    build_database([*fixture_cards(), *REAL, *EXTRA], settings.cards_db_path, meta={"bulk_type": "test"})
    repo = CardRepository(settings.cards_db_path, ImageStore(settings.images_dir))
    yield repo
    repo.close()


def decision(s):
    d = s.state.rules.decision
    assert d is not None, "no decision"
    return d


def answer(s, prefer="p2"):
    """Answer the pending choices of a spell being cast (its target: Bob) until the next free-cast choice or none."""
    for _ in range(6):
        d = s.state.rules.decision
        if d is None or "without paying" in d.prompt:
            return
        ids = [o.id for o in d.options]
        act(s, d.player, type="choose", decision_id=d.id, option_ids=[prefer] if prefer in ids else ids[: max(1, d.min_choices)])


def check(s):
    replay_matches(s)
    replay_matches(reloaded(s))
    assert reloaded(s).state.model_dump(mode="json") == s.state.model_dump(mode="json")


def test_a_sorcery_only_free_cast_offers_only_the_sorcery_half(cards):
    s = build(cards, [*NAMES, "Giant Growth"], theirs=["Llanowar Elves"])
    elves = put(s, "Llanowar Elves", "p2")
    aisha = put(s, "Aisha of Sparks and Smoke")
    s.state.rules.controlled_since[aisha.id].turn = 0
    split = card_named(s, "Consecrate // Consume")
    growth = card_named(s, "Giant Growth")
    act(s, "p1", type="move", card_ids=[split.id, growth.id], to={"zone": "hand"})
    mana(s, G=1)
    act(s, "p1", type="cast_spell", card_id=growth.id, targets=[aisha.id])  # (Aisha: 4 + 3 + 1 prowess = 8 damage)
    pass_until_stack_empty(s)
    act(s, "p1", type="pass_priority")
    act(s, "p1", type="declare_attackers", attackers=[{"card_id": aisha.id, "target": "p2"}])
    for _ in range(30):
        d = s.state.rules.decision
        if d is not None and d.kind == "choose_cards":
            break
        if d is not None and d.kind == "declare_blockers":
            act(s, d.player, type="declare_blockers", blocks=[])
        else:
            act(s, s.state.rules.priority, type="pass_priority")
    d = decision(s)
    assert [o.label for o in d.options] == ["Consume"]  # (the whole card was offered, and Consecrate, an instant, was cast)
    life = s.state.players["p1"].life
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])
    answer(s)  # (Consume's target: Bob)
    pass_until_stack_empty(s)
    assert s.state.cards[split.id].zone == "p1:graveyard"
    assert s.state.cards[elves.id].zone == "p2:graveyard" and s.state.players["p1"].life == life + 1  # Consume resolved (709.3b)
    check(s)


def test_an_engine_free_cast_takes_no_face_from_the_cast(cards):
    s = build(cards, [*NAMES, "Delver of Secrets // Insectile Aberration"])
    delver = card_named(s, "Delver of Secrets // Insectile Aberration")
    act(s, "p1", type="move", card_ids=[delver.id], to={"zone": "exile"})
    s.state.rules.free_casts.append(delver.id)  # (as cascade or suspend leave it when another choice is pending)
    with pytest.raises(ActionError):
        act(s, "p1", type="cast_spell", card_id=delver.id, free=True, face=1)  # (it entered transformed)
    assert s.state.cards[delver.id].zone == "p1:exile"


def gix_ready(s, tops):
    """Gix on Alice's battlefield, ``tops`` on top of Bob's library (first on top), as many Forests in her hand to discard."""
    gix = put(s, "Gix, Yawgmoth Praetor")
    s.state.rules.controlled_since[gix.id].turn = 0
    ids: list[str] = []
    for name in reversed(tops):
        c = next(c for c in s.state.cards.values() if c.name == name and c.owner == "p2" and c.zone == "p2:library" and c.id not in ids)
        act(s, "p2", type="move", card_ids=[c.id], to={"zone": "library"}, position="top")
        ids.append(c.id)
    for _ in tops:
        act(s, "p1", type="move", card_ids=[next(c.id for c in s.state.cards.values() if c.zone == "p1:library" and c.name == "Forest")],
            to={"zone": "hand"})
    mana(s, B=3, C=4)
    act(s, "p1", type="activate_ability", card_id=gix.id, ability=1, targets=["p2"], x_value=len(tops))
    for _ in range(12):
        d = s.state.rules.decision
        if d is not None and "without paying" in d.prompt:
            break
        if d is None:
            act(s, s.state.rules.priority, type="pass_priority")
        else:  # (the cards to discard: X of them)
            act(s, d.player, type="choose", decision_id=d.id, option_ids=[o.id for o in d.options][: max(1, d.min_choices, len(tops))])
    return list(reversed(ids))


def test_gix_plays_only_as_many_lands_as_land_plays_are_left(cards):
    s = build(cards, NAMES, theirs=["Breeding Pool", "Lightning Bolt"])
    put(s, "Exploration")  # two land plays this turn (305.2)
    pool, bolt, island, island2 = gix_ready(s, ["Breeding Pool", "Lightning Bolt", "Island", "Island"])
    d = decision(s)
    assert {o.card_id for o in d.options} == {pool, bolt, island, island2}
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[pool])
    d = decision(s)
    assert "life" in d.prompt and s.state.cards[pool].zone == "p2:exile"  # 614.12a: asked before it enters
    s = reloaded(s)  # (a save and a load in the middle of "any number of them")
    act(s, "p1", type="choose", decision_id=d.id, option_ids=["pay"])
    d = decision(s)
    assert {o.card_id for o in d.options} == {bolt, island, island2}  # the same instruction goes on
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[bolt])
    answer(s)
    d = decision(s)
    assert {o.card_id for o in d.options} == {island, island2}  # (the Bolt waits on the stack, 608.2g)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[island])
    d = s.state.rules.decision
    assert d is None or not d.options  # 305.2b: both land plays are used; the other Island isn't offered
    if d is not None:
        act(s, "p1", type="choose", decision_id=d.id, option_ids=[])
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None and not s.state.zones.get("stack")
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 2
    assert s.state.cards[pool].zone == s.state.cards[island].zone == "p1:battlefield" and not s.state.cards[pool].tapped
    assert s.state.cards[island2].zone == "p2:exile" and s.state.cards[bolt].zone == "p2:graveyard"
    assert s.state.players["p1"].life == 38 and s.state.players["p2"].life == 37
    check(s)


def test_cards_of_a_player_who_left_mid_choice_cant_be_played(cards):
    from tests.test_rules_wave22d_review import build3

    s = build3(cards, NAMES)
    put(s, "Exploration")
    islands = gix_ready(s, ["Island", "Island"])
    d = decision(s)
    assert {o.card_id for o in d.options} == set(islands)
    act(s, "p2", type="concede")  # 800.4a: Bob's cards leave the game with him; Alice is still choosing
    d = decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[d.options[0].id])  # (asked again without them: nothing is left)
    pass_until_stack_empty(s)
    assert s.state.rules.decision is None and all(s.state.cards[i].zone == "p2:exile" for i in islands)
    assert s.state.rules.lands_this_turn("p1", s.state.turn.number) == 0
    check(s)


def test_djinn_casts_an_x_spell_with_x_0(cards):
    s = build(cards, NAMES)
    djinn = put(s, "Djinn of Wishes")
    s.state.rules.controlled_since[djinn.id].turn = 0
    act(s, "p1", type="counter", card_ids=[djinn.id], kind="wish", delta=3)
    blaze = card_named(s, "Blaze")
    act(s, "p1", type="move", card_ids=[blaze.id], to={"zone": "library"}, position="top")
    mana(s, U=2, C=2)
    act(s, "p1", type="activate_ability", card_id=djinn.id, ability=2)
    pass_until_stack_empty(s)
    d = decision(s)
    act(s, "p1", type="choose", decision_id=d.id, option_ids=[blaze.id])
    answer(s)
    pass_until_stack_empty(s)
    assert s.state.cards[blaze.id].zone == "p1:graveyard" and s.state.players["p2"].life == 40  # 107.3b: Blaze dealt 0
    check(s)
