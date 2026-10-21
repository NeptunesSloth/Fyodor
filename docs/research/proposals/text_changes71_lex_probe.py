import importlib.util,sys
from pathlib import Path
p=Path('/workspace/Fyodor/docs/research/proposals/text_changes71_lex.py');s=importlib.util.spec_from_file_location('lex71',p);m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m)
from app.rules.characteristics import printed_from_data
from tests.fixtures.cards import card
cases=[('color','black','green','Black Knight has protection from black. Destroy target nonblack creature.','Black Knight has protection from green. Destroy target nongreen creature.',('Black Knight',)),('basic_land','Swamp','Plains','Swampwalk; search for two Swamps.','Plainswalk; search for two Plains.',()),('basic_land','Island','Forest','Island Fish Jasconius has islandwalk.','Island Fish Jasconius has forestwalk.',('Island Fish Jasconius',)),('creature','Goblin','Elf','Goblin King gives Goblins +1/+1.','Goblin King gives Elves +1/+1.',('Goblin King',)),('creature','Goblin','Elf','Search for a card named Goblin King and all Goblins get +1/+1.','Search for a card named Goblin King and all Elves get +1/+1.',())]
for category,old,new,text,expected,names in cases:
 got=m.word_text(text,m.TextChange71(category=category,old=old,new=new),names=names,catalog_names=('Goblin King',));assert got==expected,(got,expected)
c=printed_from_data(card('Swamp',type_line='Basic Land — Swamp',oracle_text='',colors=[],color_identity=['B']))
r=m.apply(c,m.TextChange71(category='basic_land',old='Swamp',new='Island'));assert r.name=='Swamp' and r.subtypes==frozenset({'Island'});assert any(a.text=='{T}: Add {U}.' for a in r.abilities) and not any(a.text=='{T}: Add {B}.' for a in r.abilities)
print('lexical5 + native intrinsic mana1 PASS')

for old,new,text,expected in [('Merfolk','Goblin','a Merfolk','a Goblin'),('Time Lord','Goblin','Time Lord creatures','Goblin creatures'),('Goblin','Time Lord','Goblin creatures','Time Lord creatures')]:
    assert m.word_text(text,m.TextChange71(category='creature',old=old,new=new),names=())==expected
assert m.word_text('Choose a card named Gin and Tonic and all red creatures.',m.TextChange71(category='color',old='red',new='blue'),names=(),catalog_names=('Gin and Tonic',))=='Choose a card named Gin and Tonic and all blue creatures.'
print('invariant+multiword3/catalog-bound-and1 PASS')
