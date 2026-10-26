"""-- (wave 110B) -- Stangg, Echo Warrior: "Whenever Stangg attacks, create Stangg Twin, a legendary 3/4 red and green Human Warrior creature token. It enters
tapped and attacking. For each Aura and Equipment attached to Stangg, create a token that's a copy of it attached to Stangg Twin. Sacrifice all tokens created
this way at the beginning of the next end step."

* 508.4: the Twin enters attacking (never declared); 707.2 / 111.4: each token copies the Aura or Equipment as it is (a token one is copied too); 303.4f, 301.5:
  the copy enters attached to the Twin; rulings 2022-09-09: an Aura copy that can't be attached to the Twin isn't created, an Equipment copy that can't
  be attached enters unattached (token_copy_continuations.attached is the same entry path); the sacrifice affects every token created this way, but only those
  still under your control (701.21).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.rules.plan import Plan

Context = dict[str, Any]
_TWIN = "stangg_twin110b"
_ALL = "stangg110b"
_TEXT = ("Create Stangg Twin, a legendary 3/4 red and green Human Warrior creature token. It enters tapped and attacking. For each Aura and Equipment attached to "
         "~, create a token that's a copy of it attached to Stangg Twin. Sacrifice all tokens created this way at the beginning of the next end step.")


def parse(body: str) -> tuple[list[dict[str, Any]], Any, bool] | None:
    from app.rules import scripts

    text = re.sub(r"\bStangg\b(?! Twin)", "~", body.strip().replace("~ Twin", "Stangg Twin"))
    if text[:1].upper() + text[1:] != _TEXT:
        return None
    got = scripts.parse_effects(_TEXT.split(" For each")[0])
    if got is None or got[1] is not None or len(got[0]) != 1 or got[0][0].get("do") != "create_attacking":
        return None
    return [{**got[0][0], "as": _TWIN}, {"do": "stangg_copies110b"}], None, False


def copies(plan: Plan, ctx: Context, e: dict[str, Any]) -> bool:
    from app.rules import context, copying
    from app.rules import replace as replacement

    twin = context.objects(plan, ctx, _TWIN)
    jobs = ctx.get("stangg_jobs110b")
    if jobs is None:
        jobs = []
        source = plan.state.cards.get(ctx.get("source_card") or "")
        host = context.ref_of(plan, twin[0]) if twin else None
        if source is not None and host is not None:
            for original in plan.state.cards.values():
                if original.attached_to == source.id and original.zone.endswith(":battlefield") and plan.ch(original).subtypes & {"Aura", "Equipment"}:
                    jobs.append({"recipe": copying.recipe_of(plan, original).model_dump(mode="json"), "host": host.model_dump(mode="json")})
        ctx["stangg_jobs110b"] = jobs
    requests, refs = [], []
    for job in jobs:
        request = copying.token_copy_request(plan, ctx, ctx["controller"], copying.CopyRecipe.model_validate(job["recipe"]), 1)
        if request is not None:
            requests.append(request)
            refs.append(job["host"])
    made = replacement.create_token_batch(plan, requests, ctx=ctx, bind=None, then=replacement.rerun_then(ctx, e), attachment_refs=refs,
                                          creation_atoms=["attachment:" + str(i) for i in range(len(requests))]) if requests else []
    if made is None:
        return False
    context.bind_objects(plan, ctx, _ALL, [*twin, *made])
    at = int(ctx.get("next") or 0)
    ctx["effects"][at:at] = [{"do": "schedule_copy_cleanup", "what": "sacrifice", "whose": "next", "ref": "ref:" + _ALL}]
    return True


PRIMITIVES = {"stangg_copies110b": copies}
