p='app/rules/wave110c_misc.py'
t=open(p).read()
code='''WARP_WORLD = ("Each player shuffles all permanents they own into their library, then reveals that many cards from the top of their library. Each player puts all artifact, "
              "creature, and land cards revealed this way onto the battlefield, then does the same for enchantment cards, then puts all cards revealed this way that weren't put "
              "onto the battlefield on the bottom of their library.")


def warp_world() -> Any:
    return [{"do": "warp_shuffle110c"}, {"do": "warp_enter110c", "kinds": "main"}, {"do": "warp_enter110c", "kinds": "ench"}, {"do": "warp_bottom110c"}], None, False


def warp_shuffle(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Warp World: in turn order each player counts the permanents they own (tokens too; a commander that goes to the command zone still counts, per the Gatherer rulings
    2009-10-01 / 2019-05-03), shuffles them in, and reveals that many cards (111.1: tokens aren't cards: the ones shuffled in are skipped, 704.5d removes them later)."""
    from app.rules import effects

    ctx["warp110c"] = {}
    for pid in plan.apnap():
        owned = [c.id for c in plan.state.cards.values() if c.owner == pid and c.zone.endswith(":battlefield")]
        if owned:
            plan.do({"type": "move", "card_ids": owned, "to": {"player": pid, "zone": "library"}}, actor=pid)
        effects.shuffle_library(plan, ctx, {"do": "shuffle_library", "who": f"player:{pid}"})
        top = [c for c in effects._library(plan, pid) if not plan.state.cards[c].is_token][:len(owned)]
        for at in range(0, len(top), 250):
            plan.do({"type": "reveal", "card_ids": top[at:at + 250]}, actor=pid)
        ctx["warp110c"][pid] = top
    return True


def warp_enter(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Warp World: every player's artifact, creature and land cards enter together; then the enchantment cards (Auras choose what to enchant in turn order, 303.4f, and not
    the enchantments entering with them)."""
    from app.rules import attachments

    want = {"Artifact", "Creature", "Land"} if e["kinds"] == "main" else {"Enchantment"}
    entries = [{"card": c, "player": pid, "actor": pid, "tapped": False} for pid in plan.apnap() for c in ctx["warp110c"].get(pid, [])
               if plan.state.cards[c].zone == f"{pid}:library" and want & set(plan.ch(plan.state.cards[c]).types)]
    return attachments.enter(plan, entries, ctx) if entries else True


def warp_bottom(plan: Plan, ctx: dict[str, Any], e: dict[str, Any]) -> bool:
    """Warp World: the revealed cards that stayed go to the bottom of their owner's library, in an order that owner picks (401.4)."""
    from app.rules import effects

    queue = []
    for pid in plan.apnap():
        rest = [c for c in ctx["warp110c"].get(pid, []) if plan.state.cards[c].zone == f"{pid}:library"]
        if len(rest) == 1:
            effects.bottom_at_random(plan, pid, rest, actor=pid)
        elif rest:
            queue.append({"owner": pid, "cards": rest, "place": "bottom"})
    if not queue:
        return True
    first = queue.pop(0)
    ctx["library_queue"] = queue
    effects._ask_order(plan, ctx, first["owner"], first["owner"], first["cards"], "bottom")
    return False


'''
i=t.index('RESUME = {')
t=t[:i]+code+t[i:]
t=t.rstrip('\n')+'\nPRIMITIVES.update({"warp_shuffle110c": warp_shuffle, "warp_enter110c": warp_enter, "warp_bottom110c": warp_bottom})\n'
open(p,'w').write(t)
p='app/rules/wave110c_core.py'
t=open(p).read()
t=t.replace('BUILDERS: dict[str, Callable[[], Parsed]] = {\n','BUILDERS: dict[str, Callable[[], Parsed]] = {\n    wave110c_misc.WARP_WORLD: wave110c_misc.warp_world,  # -- Warp World (wave 110C) --\n',1)
t=t.replace('from app.rules import wave110c_any\n','from app.rules import wave110c_any, wave110c_misc\n',1)
open(p,'w').write(t)
