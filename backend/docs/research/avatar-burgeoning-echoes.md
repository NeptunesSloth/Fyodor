# Avatar of Burgeoning Echoes: collateral validation

Canonical production Oracle has landfall empowering Jace 2 and a static grant giving planeswalkers you control “[-10]: Put a +1/+1 counter on target creature for each land you control.” Its completion follows the shared allowance for quoted loyalty-ability grants; this card needs no runtime change.

Actual Avatar casting and a native land play create the blue Jace planeswalker token with two loyalty counters and its native surveil/draw abilities. The grant belongs to each affected planeswalker, so its activation pays that host's loyalty rather than the Avatar's. Spending the token's final ten counters sends the zero-loyalty planeswalker through state-based actions before the independent stack ability resolves. Removing the Avatar afterward does not remove that stack ability. The source creature itself has no loyalty and survives normally, since zero-loyalty state-based actions apply only to planeswalkers.

The grant shares its host's ordinary once-per-turn loyalty limit with native abilities, retains sorcery timing, and applies only to its controller's planeswalkers. Different hosts have independent activation limits. Native Jace draw/surveil gameplay is also validated, including draw after the token dies from paying its last three loyalty.

Eight canonical gameplay/save/replay cases pass; no application code was changed for this validation. Log: `/tmp/fyodor-avatar-echoes-eight-final.log`.
