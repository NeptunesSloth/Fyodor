# Targeting as though hexproof were absent

Detection Tower, Nowhere to Run, Glaring Spotlight, and Kaya, Bane of the Dead use a
shared rule permission. It does not remove abilities or bypass shroud or protection
(CR 609.4, 702.11). Hexproof from a quality is covered too. Glaring Spotlight and Kaya
apply to spells and abilities their controller controls; Nowhere to Run's permission
is broader. Kaya and Detection Tower also cover opposing players, and Kaya covers
noncreature permanents.

Static permissions stop when their source leaves, so targets are checked again during
resolution. Nowhere to Run also suppresses opposing creatures' ward at the targeting
event; leaving later does not retroactively cause a ward trigger. It does not remove
ward or suppress other targeting triggers.

Detection Tower stores a rule-changing permission until cleanup, rather than a list
of current creatures. Creatures entering or changing control later are affected
(CR 611.2c). Its effect persists after the land leaves. The official rulings supporting
these distinctions are saved in `research/hexproof_targeting_rulings.json`.

Thirty-seven focused scenarios pass with replay/save-load, covering ordinary and
qualified hexproof, player shields, shroud/protection, third-player scope, noncreature
permanents, source departure, real entry triggers, later entrants, and expiration.
