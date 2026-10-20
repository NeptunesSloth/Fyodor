# Canoptek Spyder: a compound selector union

Canonical Oracle text triggers whenever another nontoken artifact creature or Vehicle its controller controls enters. “Artifact creature” is an intersection; Vehicle is the other branch. Neither ordinary artifacts nor ordinary creatures qualify. The shared “another,” “nontoken,” and controller restrictions apply to both branches.

The selector grammar now represents a qualified compound permanent-type branch OR a recognized subtype as two complete native `Selector.either` branches. Each branch is independently parsed with its shared qualifiers. No trigger dispatcher or effect implementation changes are needed. Matching both branches still produces one match, so an animated Vehicle entering produces one trigger (CR 603.2c).

Canonical gameplay tests cast the Spyder and eligible/ineligible permanents; check opponents' cards and tokens; and use March of the Machines plus Smuggler's Copter to exercise an actual object matching both branches without double drawing. Every scenario verifies replay/save behavior. Selector assertions check the artifact-creature intersection, both branches' restrictions, and refusal of unknown subtype words. Existing selector suites guard the shared parser.
