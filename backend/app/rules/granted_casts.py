"""-- granted casts (wave 29B) -- the "cast it?" choice of a cast the engine grants as an effect resolves: cascade, discover, ripple, suspend and
rebound ("you may cast that card without paying its mana cost"). Researched against the Comprehensive Rules of 2026-09-25 and the Gatherer
rulings of Bloodbraid Elf (cascade), Trumpeting Carnosaur (discover), Rift Bolt (suspend), Staggershock (rebound), Thrumming Stone (ripple).

* 608.2g: the cast follows 601.2a-i as the ability resolves. 709.3, 709.3a: a split card is cast as one half and only that half is evaluated;
  715.3, 715.3a: an adventurer card is cast as the creature or as its Adventure; 712.11b-c: a modal double-faced card as either face. Each way to
  cast the card is therefore its own option (``card@face``, as permissions.free_cast offers them: ``permissions.play_faces``), and a land face is
  never cast (712.12; a land is played, not cast): only suspend, which says "play it" (702.62a), offers it, while its owner has a land play left
  on their own turn (305.2a-b, 305.3), and plays it as the ability resolves (``permissions.play_land_now``).
* 702.85a cascade: "… exile cards … until you exile a nonland card whose mana value is less than this spell's mana value. You may cast that card
  without paying its mana cost if the resulting spell's mana value is less than this spell's mana value." The card in exile has the characteristics
  of its front face / its combined halves / its creature (709.4b, 712.8a, 715.4), the *spell* those of the face being cast: each option is checked
  on its own (the Gatherer ruling of 2021-06-18: "the resulting spell you cast must also have lesser mana value"; "you may cast either half but not
  both halves").
* 701.57a discover N: the same with "mana value … N or less" (Gatherer, 2023-11-10: Galvanic Giant, 4, can be cast at discover 4, its Adventure
  Storm Reading, 7, only at discover 7 or more).
* 702.62a suspend, 702.88a rebound, 702.60a ripple: no limit; any half / face, cast without paying (a ripple card has the same name as the spell:
  201.2a, 709.4a: one name in common is enough, a split card having two).
* 601.3: a half / face that a rule or effect prohibits casting (cast_limits) is not offered; with none left the card is not cast and the declined
  outcome (to the bottom, into the hand, left exiled) happens at once.

The answer is "yes" (the card as it is, its first half / front face), "yes@1" (its second half / back face) or "no"; the face an answer names is
the only one ``casting.cast_free`` accepts (``RulesState.free_cast_faces``). Old saves asked a plain yes / no, which still resolves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.game.rules_state import DecisionOption
from app.rules.plan import decide

if TYPE_CHECKING:
    from app.game.rules_state import RulesState
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan


def faces(plan: Plan, player: str, cid: str, *, below: int | None = None, at_most: int | None = None,
          play: bool = False) -> list[tuple[int | None, Characteristics]]:
    """Each way ``player`` could cast the card ``cid`` now: (face, the spell's characteristics) of every half / face that is a spell, whose mana
    value is less than ``below`` (cascade) / at most ``at_most`` (discover) and that nothing prohibits casting (601.3). ``play``: a land face is
    one too while the player has a land play left (suspend: "play it", 702.62a; 305.2a-b, 305.3)."""
    from app.rules import cast_limits, casting, land_plays, permissions

    card = plan.state.cards[cid]
    out: list[tuple[int | None, Characteristics]] = []
    for face, ch in permissions.play_faces(plan, card):
        if ch.is_land:
            if play and land_plays.open_for_effect(plan.state, player, plan.info):
                out.append((face, ch))
            continue
        if not ch.types:
            continue
        if (below is not None and ch.mana_value >= below) or (at_most is not None and ch.mana_value > at_most):
            continue
        if cast_limits.cast_problem(plan.state, player, card, ch, plan.info, resolving=True) is None \
                and casting.free_cast_problem(plan, player, card, ch) is None:  # (review 29B: no answer may be a dead end, 601.2c / 601.5)
            out.append((face, ch))
    return out


def ask(plan: Plan, ctx: dict[str, Any], *, player: str, cid: str, head: str, no: str, decline: str | None = None,
        below: int | None = None, at_most: int | None = None, group: list[str] | None = None, play: bool = False) -> bool:
    """Ask ``player`` whether to cast the card, offering every way to cast it (``faces``). True when nothing was asked because the card can't be
    cast, its declined outcome (``decline``, effects.leave_uncast) already done; False while the question is pending (resume: "suspend_cast").
    ``group``: the cards already put on the bottom of the library with it in mind (cascade: a declined card joins them in a random order)."""
    from app.rules import effects, permissions

    card = plan.state.cards[cid]
    found = faces(plan, player, cid, below=below, at_most=at_most, play=play)
    if not found:
        plan.note(f"{card.name} can't be cast without paying its mana cost now", [cid])
        effects.leave_uncast(plan, player, cid, decline, group or ())
        return True
    plan.rules.free_casts.append(cid)
    both = len(permissions.play_faces(plan, card)) > 1
    options = [DecisionOption(id="yes" if not face else f"yes@{face}",
                              label=f"{'Play' if ch.is_land else 'Cast'} {ch.name}" if both else "Play it" if ch.is_land else "Cast it")
               for face, ch in found]
    decide(plan, player=player, kind="choose_one", prompt=f"{head}: cast {card.name} without paying its mana cost?",
           options=[*options, DecisionOption(id="no", label=no)],
           resume={"step": "suspend_cast", "ctx": ctx, "card": cid, **({"decline": decline} if decline else {}), **({"group": group} if group else {})},
           source=card)
    return False


def face_ok(r: RulesState, card_id: str, face: int | None) -> bool:
    """May the engine's free cast of this card be made as ``face``? Only the one its choice named ("yes@1"); else the first (a client can't pick)."""
    return (face or 0) == r.free_cast_faces.get(card_id, 0)
