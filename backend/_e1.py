p='app/rules/values.py'; s=open(p).read()
old='''the number of .+)$", what)'''
assert old in s
s=s.replace(old,'''the number of .+|the amount of mana spent to cast that spell)$", what)''',1)
open(p,'w').write(s)
p='app/rules/trigger_words.py'; s=open(p).read()
old='''    if cond is not None and cond.get("event") == "cast" and cond.get("targets") == "self":'''
new='''    if (cond or {}).get("event") == "cast":  # -- triggers (wave 21B) -- "Whenever you cast a spell, you lose life equal to its mana value"
        body = re.sub(r"^((?:you )?(?:lose|gain)s? life equal to) its mana value\\.$", r"\\1 that spell's mana value.", body)
        body = re.sub(r"^(if the amount of mana spent to cast it was less than its mana value, .+? equal to) the difference\\.$",
                      r"\\1 that spell's mana value minus the amount of mana spent to cast that spell.", body)
    if cond is not None and cond.get("event") == "cast" and cond.get("targets") == "self":'''
assert old in s
s=s.replace(old,new,1); open(p,'w').write(s)
p='app/rules/conditions.py'; s=open(p).read()
old='''    if _SPENT_OVER_PT.fullmatch(t):'''
new='''    if t == "the amount of mana spent to cast it was less than its mana value":  # -- triggers (wave 21B) -- the cast spell's total cost vs its mana value
        return {"object": "it", "cast": {"total": "under_mv", "event_spell": True}}
    if _SPENT_OVER_PT.fullmatch(t):'''
assert old in s
s=s.replace(old,new,1)
old='''    if need == "over_min_pt":'''
new='''    if need == "under_mv":  # -- triggers (wave 21B) -- 202.3b: an X spell's mana value on the stack counts X (not modelled): not judged
        spell = plan.state.cards.get(record.card)
        if spell is None or "{X}" in plan.ch(spell).mana_cost:
            return False
        return sum(record.mana_spent.values()) < plan.ch(spell).mana_value
    if need == "over_min_pt":'''
assert old in s
s=s.replace(old,new,1); open(p,'w').write(s)
