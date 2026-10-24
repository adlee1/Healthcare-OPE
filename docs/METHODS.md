# Methods and interpretation

This document describes the adopted local implementation behind the reported results. It is an independent, partial empirical reproduction of [APRIL](https://proceedings.mlr.press/v297/mandyam26a.html), not the authors' official implementation. Cohort construction and undisclosed statistical details involve explicit local choices.

## Tasks, groups, and patients

The task is single-step contextual-bandit offline policy evaluation in local non-ICU MIMIC-IV 3.1 cohorts. The discrete action sets are potassium `{0,10,20,40}` and sodium `{0,100,200,300,400,500}`, using the locally verified mEq mapping. Treatment timing, outcome selection, and eligibility rules are implementation choices; matching the paper's patient counts was not an optimization target.

The sodium gender case uses female patients as the behavior population and male patients as the target population. In the potassium dose-shift case, patients with any eligible 40 mEq event enter the target population; other patients enter the behavior population. All eligible events of an assigned patient are retained, so target patients can also have zero- or lower-dose events.

A fixed patient-key hash assigns approximately 80%/20% train/validation folds. Roles and folds remain fixed throughout bootstrap sampling. Patients do not cross training and validation; there is no additional untouched test set in these reported results.

| Fixed population | Sodium gender: patients / events | Potassium dosage: patients / events |
|---|---:|---:|
| Behavior train | 107 / 4,671 | 16,469 / 552,518 |
| Behavior validation | 22 / 863 | 4,133 / 141,671 |
| Target train | 82 / 5,095 | 5,172 / 347,258 |
| Target validation | 15 / 1,494 | 1,306 / 81,538 |

Behavior validation is not sampled in the main DM/DM+ bootstrap. The sodium target-validation events contain 1,493 zero actions and one 100 mEq action. The potassium target-validation action counts for `{0,10,20,40}` are `{79,148;20;413;1,957}`; its behavior training population contains no action 40. Predictions for that action therefore depend on reward-model extrapolation.

## Models and annotation budgets

Models use 15 pretreatment features: age, gender, weight, height, heart rate, respiratory rate, oxygen saturation, systolic and diastolic blood pressure, creatinine, and indicators for saline 0.9%, dextrose 5%, propofol, norepinephrine, and insulin. Identifiers, cohort roles, retrospective disease labels, and post-treatment outcomes are not predictors.

Preprocessing is fitted only on the respective model's training data. Continuous features use median imputation and standardization; binary features use mode imputation, with ties assigned zero. Entirely missing or constant columns follow the recorded omission rules. The target policy is fitted by L2-regularized logistic regression; single-action training draws use the defined constant-policy case.

DM fits ordinary least squares with an intercept, transformed context, and numerical dose divided by the task maximum. It has no context-action interaction and does not clip predictions. DM+ adds valid counterfactual rows to the same factual training population and refits the same OLS model, retaining the factual-only preprocessing. LLM predictions of post-treatment laboratory values are converted to rewards through the adopted reward formula with `sigma=2.5`.

Annotation budgets `{0,100,200,300,400,500}` are fixed prefixes of requested labels. Invalid labels remain in the request denominator and are not replaced. Valid unique CF counts are `{0,100,200,300,397,497}` for sodium/DeepSeek and `{0,100,200,300,400,499}` for potassium/GPT-4o-mini. The saved request model identifiers are `deepseek-flash` and `gpt-4o-mini-2024-07-18`; offline reproduction uses the stored labels rather than new model calls.

## Paired patient bootstrap

Each of 500 draws independently resamples patients with replacement within behavior train, target train, and target validation, retaining each group's original patient count. A sampled patient's events inherit that patient's multiplicity. The policy-value estimate and observed reference weight the resulting repeated events equally; they are not averages of equally weighted patient means.

Each original draw refits the target policy and DM, including their training preprocessing. DM+ shares that draw's target policy, factual preprocessor, evaluation population, and observed reference. Counterfactual rows inherit the same behavior-patient multiplicity as their factual source rows. LLM generation randomness is not resampled. Different methods and budgets share the original draw identities; failed draws are not replaced.

The reference is the observed target-validation reward mean in each draw, not known causal target-policy value. Because the target policy is refitted, the reported variation also includes policy-fitting variation.

## Statistics

Let `e_m,b = V_hat_m,b - V_ref,b` and `B=500`.

| Quantity | Definition and interpretation |
|---|---|
| RMSE | `sqrt(mean_b(e_m,b^2))`; error relative to the observed proxy |
| Relative improvement | `100 × (RMSE_DM − RMSE_DMplus) / RMSE_DM` |
| Curve error bar | `± SD(e_m,b^2) / (2 × sqrt(B) × RMSE)`; finite-bootstrap Monte Carlo SE, not a 95% CI or patient-population RMSE sampling SE |
| Paired t-test | Two-sided test of `e_DM,b^2 − e_DMplus,b^2`, with 499 degrees of freedom; conditional Monte Carlo comparison |
| Absolute-error-gain interval | 2.5th/97.5th percentiles of `abs(e_DM,b) − abs(e_DMplus,b)`, using linear interpolation; not a confidence interval for the RMSE difference |

All reported p-values are unadjusted. More bootstrap draws can reduce Monte Carlo uncertainty without adding independent patients. Neither the t-test nor the error-bar calculation is claimed to recover the original paper's undisclosed statistical construction.

| At 500 requests | Sodium gender / DeepSeek | Potassium dosage / GPT-4o-mini |
|---|---:|---:|
| DM RMSE | 0.329760607702 | 0.000558455623 |
| DM+ RMSE | 0.305482558895 | 0.000330506060 |
| Conditional paired t | 23.0735610846 | 18.7020984159 |
| Unadjusted conditional p | 1.0534416128e-80 | 1.5385716756e-59 |
| Absolute-error-gain percentile interval | [0.000375700994, 0.050258818381] | [−0.000397263580, 0.000418567218] |

The potassium interval crosses zero despite its RMSE reduction; these statistics measure different quantities. Both cases were chosen after observing results. Together with the small sodium validation population, limited action support, fixed label cache, and proxy reference, this prevents interpreting the results as unbiased confirmation of a new method or evidence of clinical benefit. Five-model aggregate curves are retained, while multi-source annotation, action entropy, and age/gender error analyses remain outside the completed scope reported here.
