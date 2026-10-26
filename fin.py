p='app/rules/wave110c_misc.py'
t=open(p).read()
code='''FINALE_TEXT = ("You may cast up to one target instant card and/or up to one target sorcery card from your graveyard each with mana value X or less without paying their mana costs. "
               "If a spell cast this way would be put into your graveyard, exile it instead. If X is 10 or more, copy each of those spells twice. You may choose new targets for the copies.")


def finale_of_promise() -> Any:
    """Finale of Promise: two target groups (an instant card, a sorcery card: each up to one, 115.1d) sized by X, cast free one at a time like the one-target wording
    (608.2g), exiled instead of going to the graveyard (614.1a); the copies are made by :func:`finale_copy`."""
    import dataclasses

    from app.rules import scripts, selectors

    native = scripts.parse_effects("You may cast target instant card from your graveyard with mana value X or less without paying its mana cost. If that spell would be put into "
                                   "your graveyard, exile it instead.")
    if native is None or len(native[0]) != 1 or native[0][0].get("do") != "free_cast" or not isinstance(native[1], str):
        return None
    sel = selectors.from_key(native[1])
    groups = [{"what": dataclasses.replace(sel, types=(kind,)).key(), "min": 0, "max": 1} for kind in ("Instant", "Sorcery")]
    return [{**native[0][0], "n": 2}, {"do": "finale_copy110c"}], groups, native[2]


def finale_copy(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Finale of Promise: if X is 10 or more, each spell cast this way (still on the stack) is copied twice; the controller may choose new targets for each copy (707.10c)."""
    from app.rules import copying, values

    if values.evaluate(plan, ctx, {"x": 1}) < 10:
        return True
    objects = [(cid, plan.oid(cid), 2) for cid in ctx.get("free_cast_done") or [] if cid in plan.state.cards and plan.state.cards[cid].zone == "stack"]
    return copying.run(plan, copying.new_job(ctx, controller=ctx["controller"], objects=objects, retarget=True, label="Finale of Promise")) if objects else True


'''
i=t.index('PANDEMONIUM = ')
t=t[:i]+code+t[i:]
t=t.replace('PRIMITIVES = {"pandemonium110c"','PRIMITIVES = {"finale_copy110c": finale_copy, "pandemonium110c"',1)
open(p,'w').write(t)
p='app/rules/wave110c_core.py'
t=open(p).read()
t=t.replace('    wave110c_misc.WARP_WORLD: wave110c_misc.warp_world,','    wave110c_misc.FINALE_TEXT: wave110c_misc.finale_of_promise,  # -- Finale of Promise (wave 110C) --\n    wave110c_misc.WARP_WORLD: wave110c_misc.warp_world,',1)
open(p,'w').write(t)
