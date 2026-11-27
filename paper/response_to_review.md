# Response to the review

Manuscript: "Box-subdivision outer approximation: a bi-level mixed-integer method
for multimodal design optimization".

The reviewer's comments are summarized in italics, followed by the changes made.
Section names refer to the revised manuscript.

## Major comments

**M1. Adaptive repair.**

*(a) The definition includes j = i, so the stated property never holds.*

The repair is now defined over the other solved boxes, j ≠ i, in Eqs. (9)–(11). In the implementation, the column j = i of D_i is zero, so the minimum-norm least-squares solution ignores the unsatisfiable equation. The results are therefore unchanged.

*(b) Rank and inconsistency.*

The text now states three things:
- The displacements sum to zero over the intervals of each component, so the rank of D_i is at most Σ(m_j − 1).
- Beyond that number of boxes, which happens in every run in two dimensions, the system is in general inconsistent.
- The least-squares solution then reduces the excesses without cancelling them, and may modify the satisfied conditions.

*(c) Unsolved boxes.*

The text now states that lowering a cut at the solved boxes may raise it at a box not yet solved, including the box of the global minimum, and that the repair is a heuristic without validity guarantee. The frequency with which the box of the global minimizer is cut off was not measured.

*(d) Constraint cuts.*

The condition for the cuts of the constraint violation is now stated: the cut built at one box must not overestimate the violation observed at another box minus the margin.

**M2. Slopes and ablations.**

The Formulation of the sub-problem now states three things:
- At an optimum strictly inside the box, the slope vanishes and the cut is horizontal in that component.
- Slopes are non-zero only on the faces of the box.
- Their use at other boxes is an extrapolation.

The word "exact" is removed from the contributions.

A new subsection, "Ablation of the master problem and baselines spending the budget", runs two ablations from the twenty starting points: the master replaced by a random choice of unsolved boxes within the same trust region, and the slopes set to zero before the repair.

- **Two dimensions:** both ablations give the same results as the configuration, so the master problem does not contribute there.
- **Five dimensions, random choice:** the area decreases by 0.09 [0.06, 0.12], and Ackley is reached from 4 starting points against 13, a significant difference.
- **Five dimensions, zero slopes:** neither the success nor, significantly, the area changes. The ranking comes mainly from the observed values through the repair.

These findings are now stated in the discussion, the limitations, the abstract and the conclusions.

Random-order enumeration is added as the reference for Table 1: about 640 evaluations, against which the outer approximation costs a quarter to two thirds. Random slopes were not run.

**M3. Bi-level problem and convexification.**

*(a) The problem actually solved.*

The text after Eq. (3) now states that v is the value returned by a local optimizer, possibly stopped by its iteration limit. It is neither the value function nor necessarily continuous, the master problem provides no lower bound, and the method is a heuristic.

*(b) Validity with a large κ.*

The claim that a large κ makes the cuts valid by construction is removed. The text now says that no value is known to make them valid.

*(c) Effect of κ.*

The effect of κ in the master problem is now stated as a lowering of 2κ/n_c per changed component, up to 2κ, in the text and in the caption of the convexification figure.

**M4. Algorithm details.**

The implementation section and the sweep and trust-region subsections now specify:
- **Ladder:** as many values as probes, geometric over two decades below its upper bound; probe q starts at the q-th value.
- **Ladder exhaustion:** a no-good constraint, with the reason it comes after the ladder.
- **Radii:** geometric from max(Δ/2, 1) to Δ, a fractional radius admitting ⌊Δ_q⌋ changed components.
- **Radius schedule:** ×0.7 after every three iterations without improvement, down to one, and ×1.2 when the improving box lies on the border.
- **Probes within an iteration:** solved sequentially, with no-good constraints on the boxes of the previous probes.
- **Incumbent:** the feasible box of smallest value.
- **Stopping rules:** the budget, ten iterations without change of the incumbent, no new box proposed, the lower bound above the incumbent, and the maximum number of iterations.
- **MILP solver:** CBC through OR-Tools, without time limit.
- **Initial design:** an optimized Latin hypercube with a fixed seed.

Algorithm 1 refers to these rules.

**M5. Baselines and budget.**

*(a, b) DIRECT and CMA-ES stop early.*

DIRECT without local bias and with zero tolerances, and IPOP-CMA-ES, are added in the new subsection and spend the budget.
- **DIRECT without local bias:** reaches none of the optima of Rastrigin, Ackley and Styblinski–Tang in five dimensions.
- **IPOP-CMA-ES:** reaches Ackley 5-D from 19 starting points against 13 (not significant), and Rastrigin 5-D from none.

The claim on Rastrigin 5-D therefore holds against both.

*(c) EGO's budget.*

The abstract, the discussion and the conclusions now state that EGO is limited to 500 evaluations, and that with 500 evaluations no method reaches the Rastrigin 5-D minimum.

*(d) Multistart.*

The sampling is now stated (a Latin hypercube seeded by the starting point), and the text says that multistart and CMA-ES are not tuned to the budget. MLSL and the fraction of truncated local runs were not added.

*(e) Tunneling.*

The settings are now given in full: pole strength, increment and maximum, perturbation, and mobile poles. They were not tuned.

*(f) Cost of the master problem.*

A run of the configuration on Rastrigin or Ackley solves 58 to 117 MILPs, taking 1.4 to 17 s in all (20 to 190 ms each), which is most of the wall time of these runs. This is reported in the limitations. The MILP time of the cantilever was not measured.

*(g) Gradient counting.*

Now stated: a value and a gradient count as two evaluations, which favours the gradient-based methods.

**M6. Statistics.**

*(a) DIRECT is deterministic.*

The tests against DIRECT are no longer marked as significant; they are given for information, with a note in the caption and the text.

*(b) Targets.*

They are now defined in the protocol: the first study of the variants and of the multistart, CMA-ES, DIRECT and EGO baselines from five of the twenty starting points. Tunneling and the later variants are profiled against them without contributing. The same targets are used for every area. The configuration has the same area in Tables 2 and 9 because both tables use the same twenty runs of the configuration.

*(c) What was fixed before the runs.*

The tests, the measures and the targets were fixed before the twenty-start runs; the configuration was selected earlier on the same problems.

*(d) Success tolerance.*

Now stated: 10⁻⁴ max(1, |f\*|).

*(e) Uncorrected claims.*

The tests are now introduced and cited in a "Statistical tests" paragraph of the protocol: exact McNemar, Wilcoxon, Holm and bootstrap. The Ackley margin claim is replaced by the exact statement: among ten pairs, only δ = 1 against 3 differs without correction (p = 0.031), and none after Holm.

**M7. Density confound in Table 2.**

The calibrated margin, eight probes and the ladder up to 30 were rerun in five dimensions with ten subdivisions per variable. They are added as rows marked ¹, next to the existing rows for sixteen probes and the ladder up to 10.

- **Calibrated margin:** area −0.09; Ackley 1 against 13 (significant); Rastrigin 15 against 11 (not significant).
- **Eight probes:** area −0.11.
- **Ladder up to 30:** +0.01, no significant difference.
- **Ladder up to 10:** −0.03, Styblinski–Tang less often.
- **Sixteen probes:** area −0.20, Ackley less often.

The Holm correction now runs over seventeen variants, so the Rastrigin marks of the two-subdivision rows are no longer significant, and the table and text were updated. The text now gives the like-for-like results, and "eight probes, same area" is restricted to two dimensions. The swept-versus-calibrated statements now say "at the same density".

**M8. Scalability and the cantilever.**

The upper bound on the density is now argued from the rank of the displacements, Σ(m_j − 1), as a heuristic argument assessed empirically.

The boxes of the cantilever run on the port were analysed:
- After the nine initial boxes, every box differs from the incumbent in one to three of the 54 subdivided variables.
- The incumbent changes seven times, by one or two components each time.

The text now states that the method acts as a local search over the poses of a few bars on this problem. This is consistent with 540 binaries for about 63 sub-problems, which violates the paper's own condition. A basin-hopping comparison is listed as missing in the limitations and the conclusions.

**M9. Topology optimization evidence.**

*(a) Repetitions.*

These were not run. Each run on the port takes about two hours on four processes. The single-run nature and the 1% differences are stated in the text, the limitations, the conclusions and the abstract.

*(b) Two implementations.*

Table 11 and the text now separate the GGP implementation (box subdivision 82.1, multistart 83.0) from the NumPy port (box subdivision 82.3 and 82.5 with nine and sixteen probes, tunneling 82.8), and compare only within each. The abstract and the conclusions do the same.

*(c) Box-constrained solutions.*

The best designs on the port have none of their 54 subdivided variables on a face of their box. MMA without the box bounds lowers their compliance from 82.30 to 82.19 and from 82.48 to 82.35, so they are limited by the iteration limit of the sub-problems rather than by the boxes. The script is `benchmarks/cantilever/polish.py`.

*(d) Symmetries.*

Now discussed: the bars are interchangeable, and the angle interval covers each orientation four times.

*(e) Multistart initialization.*

Now stated: the lengths, thicknesses and densities are those of the reference initial design, as at the start of every sub-problem. The best-so-far curves of multistart and tunneling were not added to the figure.

*(f) Mesh sensitivity.*

Not assessed; listed in the limitations.

**M10. Inconsistencies.**

- **"An eighth to a third":** now restricted to Rastrigin 2-D, with 19 of 20 starting points, and the configuration of Table 1 is stated in its caption.
- **"Only the proposed method":** now qualified by the budget of 2500, EGO's 500 evaluations, and the absence of success at 500 evaluations.
- **Binaries:** 20, not 23, for (10, 10, 1, 1, 1), since a component with one interval adds no binary variable. The Ackley density is now given as 62 to 63 intervals per variable, since it depends on the random abscissae of the scans.
- **Range:** now defined as the spread of the function over the design space. The values are corrected: Rastrigin 2-D about 101, Ackley 22.3, and 40% instead of 54%. The fractions of Table 14 are recomputed.
- **Fraction at a tenth of the budget:** 32% in two dimensions and 25% in five.
- **Cantilever caveat:** the single-run caveat is now in the abstract.

## Minor comments

1–2. The interval indices are now written c. The ordinal constraint is explained, and named "ordinal" throughout; "Hamming" replaces "unit".

3. Eq. (6) includes λᵀ∂g/∂x_j. The absence of the bound multipliers is explained.

4. The cut of the constraint violation is described, and the no-good constraint is stated.

5. The text now says why the ladder is climbed before a no-good constraint is used.

6. The incumbent is defined, with ties resolved in favour of the box solved first.

7. The rounding of fractional radii is stated.

8. The parameters of the density estimator are given.

9. The levels are now r and the widths w_j.

10. The MILP solver is stated.

11. The Latin hypercube seed is fixed, which is stated. This defect of the initial design is reported separately to the plugin.

12. The use of the starting point by CMA-ES and EGO is stated.

13. Table 1 now has a column for the starting points reaching the optimum.

14. Not changed: the counts of truncated runs per cell of Table 3 were not added.

15. The columns of Table 10 are ordered as in Table 7.

16. The caption of Fig. 9 now explains the colour scale and the star. The text embedded in the image could not be regenerated.

17. The panel titles of Fig. 12 are rewritten and explained in the caption.

18. The logarithmic axis of Fig. 13 is stated. The figure was not regenerated, so the fonts and the additional curves are unchanged.

19. See M3(c).

20–21. Added references: Norato et al. 2015, Wein et al. 2020, Guo et al. 2014, Bonami et al. 2008, Nagarajan et al. 2019, Paulavičius and Žilinskas 2014, Sergeyev and Kvasov 2017, Auger and Hansen 2005, and Baptista and Poloczek 2018.

22. The two "competitor" statements are merged.

23. Tunneling and the ablations are added to the contributions.

24. The abstract mentions the fifth, partly multimodal function.

25. The sampling of the multistart is named.

26. The headroom factor is defined.

27. The fixed ladder bounds are stated as absolute values.

28. The unbounded ladder is defined.

29. "Hamming" is used throughout.

30. The TODO notes of the bibliography are removed. Two entries could not be verified here: the volume and pages of Stolpe (2016), and the pages of Gómez and Levy (1982). The declarations (affiliation, e-mail, funding, CRediT) remain to be completed by the author.

31. Archiving the software with a DOI remains to be done by the author.

32. The phrases "it should be noted that" are removed. The paper was not shortened further.

33. The duplicated phrase is fixed.

34. See M6(e).

35. See M3(c). No optimality gap is reported, since none is meaningful.
