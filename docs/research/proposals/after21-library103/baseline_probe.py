from app.rules.coverage import of_characteristics
from tests.test_rules_wave31d_spell_copies import characteristics
cases=[('Creature — Efreet','Whenever this creature attacks or blocks, flip a coin at end of combat. If you lose the flip, an opponent gains control of this creature.'),('Enchantment — Aura',"Enchant creature\nWhen enchanted creature attacks, return it and this Aura to their owners' hands at end of combat.")]
for kind,text in cases:
 print(kind,of_characteristics(characteristics('Probe',kind,text,spell=False)).level)
