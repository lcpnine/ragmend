Builder prompts for M0 and M1 are read verbatim from MILESTONES.md at run time.
Reviewer prompts are read verbatim from REVIEW.md.

For M2+ (no prompt block in MILESTONES.md), the owner writes `build_M2.md` etc. here,
after M1, per MILESTONES.md. The driver refuses to start a milestone without one.
