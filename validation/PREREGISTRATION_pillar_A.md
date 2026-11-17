# Pillar A pre-registration: cross-method recall estimation

Written and committed before any result of the experiment below was computed.

## Question

Does estimating recall from two arms produced by *different discovery methods* - the
included studies of a database search (arm D) and the included studies reached by
citation chasing (arm C) - give a usable estimate where version 1's provider arms do not?

Version 1 baseline (cases/coverage_summary.json in s-matysik/SnowBallSLR, 1,350
simulated evaluations, provider arms): Chapman nominal 95% interval coverage 0%,
Chao1 14%, median relative bias -8% for both.

## Design

The 270 reviews of the stopping benchmark (3 regimes x 6 graphs x 3 seed-set sizes x
5 draws). In each, the database search captures every relevant record independently
with probability q, through a mix of a shared latent prominence term (weight rho, the
same term that drives citations in the generator) and independent noise; captured
when rho*latent + (1-rho)*U > 1 - q. Seeds are drawn from arm D. Arm C is every relevant
record reached by citation chasing from the seeds, screened perfectly. Seeds are
removed from the population: truth = relevant records minus seeds, and arms are D
minus seeds and C. Grid: q in {0.5, 0.7, 0.85}, rho in {0, 0.3, 0.6}; evaluated at
chase depths 1-6 and at exhaustion.

## Criterion (fixed in advance)

Primary setting: rho = 0.3, all q and all regimes pooled, chase run to exhaustion.

GO if both hold for Chapman:
1. empirical coverage of the nominal 95% interval >= 0.80, and
2. |median relative bias of N_hat| <= 0.05.

Otherwise NO-GO: cross-method estimation is reported as a negative result in the
supplement and not offered as a feature. rho = 0 and rho = 0.6 are reported as
sensitivity, not used for the decision. Chao1 is reported alongside, not decisive.
