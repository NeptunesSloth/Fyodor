# Dragonfire Blade

Equip costs four generic mana, reduced by one for each current color of the
chosen creature (CR 601.2f, 602.2b, 702.6). The shared target-dependent equip cost
path now counts current target colors as well as target counters. Its preliminary
affordability check considers legal targets, while the final payment uses the
actual chosen target. The final generic cost cannot fall below zero.

The existing static keyword-grant parser now accepts supported "hexproof from"
abilities. Native protection-quality checks already distinguish monocolored,
multicolored and colorless spell or ability sources (CR 702.11). The Equipment
continues to grant its +2/+2 through normal layers; destroying it immediately
removes the bonus and keyword.

Canonical gameplay covers zero-, one-, two- and five-color equip targets, a
five-color unchosen creature failing to discount a colorless target, rejected
monocolored Lightning Bolt, legal multicolored Terminate, legal colorless
Ghostfire despite its red mana cost, and actual Disenchant removing the grant.
Ten focused tests and fifteen target-counter equip regressions pass, including
save/load and event-history reconstruction.
