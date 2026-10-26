"""-- wave 110A -- exchanging text boxes (612.5, layer 3 / 613.1c): Deadpool, Trading Card ("As Deadpool enters, you may exchange his text box and another
creature's.") and the shared piece for Exchange of Words.

612.5: each object loses all of its rules text and has the other's. The text each one gets is the other's rules text as the exchange begins (the effect
fixes what it exchanges, 611.2c; rules text is what the layers 1-3 give, so earlier copy or text changes count, later ones apply to the new text). Abilities
that are only granted (layer 6, 612.3) are not text, so they stay and are not moved. Self references use the object's own name afterwards (201.5), as
copying.renamed does. The effect keeps the packed text per affected object (``ContinuousEffect.text_box110a``); layers.name_changes applies it in timestamp
order with the other layer 3 effects."""
from __future__ import annotations

from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.characteristics import Characteristics
    from app.rules.plan import Plan

TEXT = "As ~ enters, you may exchange his text box and another creature's."


def pack(ch: Characteristics) -> dict[str, Any]:
    """The rules text of ``ch`` (layers 1-3): its printed abilities, not the ones borrowed or granted with a record of where from."""
    return {"name": ch.name, "oracle": ch.oracle_text,
            "abilities": [asdict(a) for a in ch.abilities if not (a.intrinsic or a.borrowed_origin or a.granted_mana_cost)]}


def apply(ch: Characteristics, packed: dict[str, Any]) -> Characteristics:
    """The object has the packed text instead of its own (612.5); the name in it becomes the object's own name (201.5)."""
    from app.rules.copying import renamed
    from app.rules.oracle import AbilityText

    def own(text: str | None) -> str | None:
        return text if text is None or packed["name"] == ch.name else renamed(text, packed["name"], ch.name)

    kept = tuple(a for a in ch.abilities if a.intrinsic or a.borrowed_origin or a.granted_mana_cost)
    new = tuple(AbilityText(**{**d, "keywords": tuple(d["keywords"]), "borrowed_origin": (), "text": own(d["text"]), "cost": own(d["cost"])}) for d in packed["abilities"])
    return replace(ch, abilities=(*new, *kept), oracle_text=own(packed["oracle"]) or "")


def exchange(plan: Plan, a: str, b: str, controller: str, source: str | None, *, duration: str = "permanent", source_card: str | None = None) -> None:
    """Exchange the text boxes of two permanents on the battlefield (612.5)."""
    from app.rules import layers

    text = {c: pack(layers.source_text71(plan.state, plan.state.cards[c], layers.copiable(plan.state, plan.state.cards[c], plan.info), plan.info)) for c in (a, b)}
    oa, ob = plan.oid(a), plan.oid(b)
    effect = layers.add_effect(plan, affected=[oa, ob], layer="3", source=source, controller=controller, duration=duration,  # type: ignore[arg-type]
                               label="Text boxes exchanged", text_box110a={oa: text[b], ob: text[a]})
    if source_card:
        effect.source_card = source_card  # "for as long as ~ remains on the battlefield" (611.2b, delayed.expire)
    plan.note(f"{plan.state.cards[a].name} and {plan.state.cards[b].name} exchange text boxes", [a, b])


EOW = "When this enchantment enters, choose two target creatures. For as long as this enchantment remains on the battlefield, exchange the text boxes of those creatures."


def definition(ability: Any, ch: Any) -> dict[str, Any] | None:
    from app.rules import scripts

    if ability.text.strip() != EOW:
        return None
    native = scripts.define(replace(ability, text="When this enchantment enters, tap two target creatures."), ch)
    if native is None:
        return None
    return {**native, "effects": [{"do": "exchange110a"}]}


def exchange_targets(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Exchange Of Words ruling (2022-10-07): if either creature is an illegal target as the ability resolves, nothing is exchanged; it lasts while the Enchantment stays."""
    from app.rules import effects

    pair = [c for c in effects._cards(plan, ctx, "target") if plan.state.cards[c].zone.endswith(":battlefield")]
    if len(pair) == 2 and plan.state.cards[ctx["source_card"]].zone.endswith(":battlefield"):
        exchange(plan, pair[0], pair[1], ctx["controller"], ctx.get("source_object"), duration="source_on_battlefield", source_card=ctx["source_card"])
    return True


PRIMITIVES: dict[str, Any] = {"exchange110a": exchange_targets}
