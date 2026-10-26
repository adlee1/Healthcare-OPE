# Model and evaluation code

[Back to the code navigation guide](CODE_GUIDE.md).

This guide maps the actual implementation in `src/april_repro/`. Line numbers refer to the repository snapshot inspected on 2026-10-26. These modules are libraries; run the supported command-line entry points instead of invoking the module files directly.

**First distinguish baseline replay from method development.** The portable `run_reproduction.py` verifies the package's recorded source hashes at [line 377](../run_reproduction.py#L377), then puts **`--package-root/src` first on `sys.path` at [line 382](../run_reproduction.py#L382)**. Its subsequent clinical imports use the frozen sources inside the restricted bundle. Editing this checkout's `src/april_repro/` therefore does not change that replay. Fresh baseline checks also compare regenerated baseline results against the saved results. Preserve these checks. A new method needs a separate, versioned research entry point that explicitly imports the checkout's sources, records its own code/configuration hashes, and writes new outputs; do not make an experimental method run by disabling provenance or equality checks.

### 1. Which “model” is which?

| Component | Actual implementation | Training inputs | Role in evaluation |
|---|---|---|---|
| Cloned policy | `PolicyFit`, fitted by `fit_policy`; scikit-learn `LogisticRegression` with L2 regularization | Pretreatment features and observed discrete actions from the supplied policy-training population | Produces action probabilities `pi(a\|x)`. In `run_dm_draw`, this is the **target-training** population. |
| DM reward model | `RewardFit`, fitted by `fit_reward`; scikit-learn `LinearRegression` | Behavior-training features, observed actions, observed lab-derived rewards | Predicts `Q(x,a)` for every allowed action. |
| DM+ reward model | The same `RewardFit` representation and OLS parameterization; `fit_augmented_reward` or `fit_paired_augmented_reward` | The same factual training rows plus valid LLM-derived counterfactual reward rows | Replaces the reward estimate in the same target-policy expectation. The target policy and evaluation population stay paired. |
| GPT-4o-mini, o3-mini, DeepSeek, Qwen, Kimi | External annotation sources, identified by `model_key` in verified annotation evidence | A previously specified clinical context and requested action, submitted through the separate annotation workflow | Their post-treatment lab predictions are mapped to rewards. These are **not five different regression architectures**, nor local policy networks. The offline core does not call these APIs. |

The reward model is additive:

```text
Q(x, a) = intercept + context_coefficients · transform(x)
          + dose_coefficient × a / max(allowed_actions)
```

There is one numerical action column, no context–action interaction, no one-hot action encoding, and no prediction clipping. Training rewards are constrained to `[0,1]`, but fitted OLS predictions may leave that interval. This is recorded rather than silently clipped. Rank-deficient designs use the fitted least-squares solution and retain rank diagnostics; there is no added ridge penalty in DM or DM+.

The policy uses `C=1.0`, `solver="lbfgs"`, `tol=1e-4`, `max_iter=1000`, `random_state=0`, `class_weight=None`, an intercept, and L2 regularization. Binary outcomes use a logistic link; more than two observed action classes use softmax. A single observed class produces a constant policy. With multiple classes but no retained context columns, the policy uses class frequencies. Unobserved action classes receive zero policy probability. See [policy parameters](../src/april_repro/clinical_models.py#L19) and [fit_policy](../src/april_repro/clinical_models.py#L324).

### 2. Data loading and feature boundaries

| Symbol and exact source location | What it does |
|---|---|
| [ClinicalDataset](../src/april_repro/clinical_dataset.py#L39), line 39 | Immutable container for feature arrays, observed actions/labs/rewards, identities, fixed roles/folds, aggregate summary, and provenance. Identity arrays support joining and sampling; they do not become predictors. |
| [ClinicalDataset.X](../src/april_repro/clinical_dataset.py#L56), line 56 | Alias for the fifteen-column feature matrix. |
| [ClinicalDataset.mask](../src/april_repro/clinical_dataset.py#L59), line 59 | Selects an event mask for a named split, role, and optional fold without copying the feature matrix. |
| [load_clinical_dataset](../src/april_repro/clinical_dataset.py#L164), line 164 | Loads an existing complete feature artifact, validates its manifest and file hashes, joins outcomes/splits by event ID, checks patient/admission identity and fixed patient assignments, recomputes rewards from observed labs, and reconciles aggregate counts. It does not construct a new cohort or query PostgreSQL. |
| [_rows](../src/april_repro/clinical_dataset.py#L77), line 77 | Streams and hashes the same CSV byte stream; verifies headers and malformed rows. |
| [_feature](../src/april_repro/clinical_dataset.py#L129), line 129 | Converts declared features to numeric values; missing values become NaN, and gender follows the fixed F=0/M=1 encoding. |
| [_check_counts](../src/april_repro/clinical_dataset.py#L154), line 154 | Reconciles events, patients, admissions, and action counts against aggregate declarations. |

The input artifact comprises `manifest.json` plus `features.csv`, `outcomes.csv`, `splits.csv`, `groups.csv`, and `summary.json`. `groups.csv` is hash-checked but never parsed into predictors. Raw missingness is preserved by the loader; imputation is fitted later on the appropriate training rows. Retrospective group labels and outcomes are not additional context features. Feature row order is preserved, which matters for original bootstrap identity.

### 3. Training, prediction, and serialization

All symbols in this table are in `clinical_models.py`.

| Symbol and line | Responsibility |
|---|---|
| [Preprocessor](../src/april_repro/clinical_models.py#L86), 86 | Validates and stores a JSON preprocessing state in the fixed fifteen-feature order. |
| [Preprocessor.transform](../src/april_repro/clinical_models.py#L124), 124 | Applies saved imputation/standardization and omits columns already marked unusable at training. It does not learn from evaluation rows. |
| [fit_preprocessor](../src/april_repro/clinical_models.py#L144), 144 | Continuous features: training median imputation, then training mean/population SD (`ddof=0`). Binary features: training mode imputation, tie → 0, no standardization. Entirely missing or constant-after-imputation columns are omitted. |
| [_Model](../src/april_repro/clinical_models.py#L183), 183 | Shared task/action/state validation and saved preprocessing. `to_dict` at 211 and `from_dict` at 215 serialize/restore coefficients and metadata. |
| [PolicyFit](../src/april_repro/clinical_models.py#L224), 224 | Serialized cloned policy; exposes convergence diagnostics and prediction. |
| [PolicyFit.predict_proba](../src/april_repro/clinical_models.py#L235), 235 | Reconstructs constant, class-frequency, binary-logistic, or softmax probabilities from saved coefficients, with columns in the full task action order. |
| [PolicyFit.predict](../src/april_repro/clinical_models.py#L276), 276 | Chooses the highest-probability action. The OPE calculation uses probabilities, not these hard predictions. |
| [RewardFit](../src/april_repro/clinical_models.py#L281), 281 | Shared DM/DM+ linear reward representation. |
| [RewardFit.predict](../src/april_repro/clinical_models.py#L293), 293 | Returns one reward prediction per supplied context/action pair. |
| [RewardFit.predict_action_values](../src/april_repro/clinical_models.py#L302), 302 | Returns an `N × number_of_actions` reward matrix for policy-value evaluation. |
| [fit_policy](../src/april_repro/clinical_models.py#L324), 324 | Fits the cloned policy with its own training-only preprocessing and saves coefficients, class support, library versions, convergence information, and iteration counts. |
| [fit_reward](../src/april_repro/clinical_models.py#L358), 358 | Fits factual OLS with an intercept and scaled numerical dose, saves factual preprocessing, and records action support/rank diagnostics. |

Both model fitters accept numeric arrays; they do not decide which population should be used. The caller supplies the selected rows. In the main bootstrap, target-policy preprocessing is fitted on target-training events, while DM preprocessing is fitted on behavior-training events. DM+ reuses the latter preprocessing.

### 4. From saved LLM predictions to a DM+ point estimate

| Symbol and source | Responsibility |
|---|---|
| [AnnotationEvidence](../src/april_repro/clinical_dmplus.py#L37), line 37 | Carries normalized annotations, original requests, aggregate summary, and provenance. |
| [Counterfactual](../src/april_repro/clinical_dmplus.py#L45), line 45 | One validated cache item: request/event identity, original event-array index, alternative action, mapped reward, model key, and protocol identity. |
| [load_verified_annotations](../src/april_repro/clinical_dmplus.py#L55), line 55 | Historical pilot-evidence loader; reconstructs the pilot summary from raw replies and receipts offline. It is not the formal five-model loader. |
| [select_counterfactuals](../src/april_repro/clinical_dmplus.py#L93), line 93 | Joins one model/split's CF consumers to original behavior-training events, rejects observed-action “counterfactuals” and duplicate event/action pairs, checks model/protocol/source identity, and converts each valid predicted lab to the fixed reward. |
| [load_model_evidence](../src/april_repro/clinical_dmplus_formal.py#L31), line 31 | Formal loader for one completed model. Revalidates planned requests, cached-pilot reuse, result/attempt/receipt chains, and factual predictions. Other models need not be complete. This original-project loader needs the full formal provenance chain; it is not the minimal portable-bundle loader. |
| [select_prefix](../src/april_repro/clinical_dmplus_formal.py#L102), line 102 | Verifies planned ranks 1–500 and selects `consumer.rank <= requested_budget` for budgets 0/100/200/300/400/500. Invalid completed labels stay inside the request denominator and are not replaced. |
| [fit_augmented_reward](../src/april_repro/clinical_dmplus.py#L151), line 151 | Point-estimate DM+: concatenates factual and valid CF rows, transforms both with the saved factual preprocessor, and refits the same equal-row-weight OLS. With no annotations, returns the original baseline object exactly. |
| [evaluate_pair](../src/april_repro/clinical_dmplus.py#L198), line 198 | Computes DM and DM+ using the same saved target policy and target-validation events. Returns both values and their differences from the observed-reward proxy. It deliberately leaves bootstrap RMSE, SE, and p-value fields unset. Empty target validation returns `not_estimable`. |
| [verify_saved_dm](../src/april_repro/clinical_dmplus.py#L250), line 250 | Checks replayed baseline status, evaluation size, value, and proxy against the saved point baseline; absolute numerical tolerance is `1e-12`. |
| [verify_evidence_unchanged](../src/april_repro/clinical_dmplus_formal.py#L136), line 136 | Rechecks source-file and plan hashes after fitting to detect changes during the run. |

The original point entry point `scripts/run_clinical_dmplus_formal.py` composes these functions. Its `fit_augmented_reward` kernel is shared with the earlier pilot despite that module's historical pilot name. Formal-prefix selection is supplied by `clinical_dmplus_formal.py`.

### 5. Original DM draws and paired DM+ draws

| Symbol and source | Responsibility |
|---|---|
| [run_dm_draw](../src/april_repro/clinical_bootstrap.py#L60), line 60 | Draws the three fixed populations (`behavior_train`, `target_train`, `target_validation`) through their population objects. Fits the target policy on repeated target-training events and DM on repeated behavior-training events. Evaluates both the DM value and the observed-reward proxy on the identical repeated target-validation events. Returns an aggregate result, fitted model payload, and draw objects. It does not refit a behavior policy. |
| [replay_original_draw](../src/april_repro/clinical_dmplus_bootstrap.py#L26), line 26 | Replays the original deterministic draw and verifies saved patient-count arrays, population identities, model metadata, seed, evaluation size, and original DM error consistency. It does not choose a new favorable draw. |
| [annotation_multiplicities](../src/april_repro/clinical_dmplus_bootstrap.py#L77), line 77 | Assigns each unique cached CF the multiplicity of its source behavior-training patient. Validates even annotations with zero draw multiplicity; rejects mixed models/protocols and duplicate cache entries. |
| [fit_paired_augmented_reward](../src/april_repro/clinical_dmplus_bootstrap.py#L108), line 108 | Expands CF rows using those integer patient multiplicities, appends them to repeated factual rows, and fits OLS. It uses explicit repeated rows, not an independent CF bootstrap or an approximate Gram-matrix update. Saved factual preprocessing remains fixed. |
| [_evaluate](../src/april_repro/clinical_dmplus_bootstrap.py#L151), line 151 | Batched paired policy expectations and observed-reference mean; also counts out-of-range OLS action predictions without clipping them. |
| [run_paired_draw](../src/april_repro/clinical_dmplus_bootstrap.py#L179), line 179 | Orchestrates replay, multiplicities, DM+ fit, and paired evaluation. Restores saved `PolicyFit`/`RewardFit`; does not refit the target policy or factual preprocessor. Replayed DM/proxy must agree with the original at `1e-12`. Zero augmentation preserves the original value exactly. |

**Record-name trap:** the DM+ draw record also stores its estimate under `dm_value` to reuse the single-method statistics schema. Its paired original baseline is `original_dm_value`. The original and augmented lists must be supplied to the paired summary in the right order.

Rows in a bootstrap draw receive equal weight *after patient repetition*. The value is therefore an average over repeated events, not an average of equally weighted patient means. Fixed original draw IDs preserve pairing across methods and budgets. LLM generation randomness is not resampled.

### 6. Statistics: the exact calculation locations

Let `e_m,b = V_hat_m,b - V_observed_proxy,b`. The observed mean is a reference proxy, not known causal target-policy value.

| Symbol and source | Calculation / contract |
|---|---|
| [clinical_bootstrap_statistics._metrics](../src/april_repro/clinical_bootstrap_statistics.py#L87), line 87 | Calculates `sqrt(mean(e_b^2))`, bootstrap SD of estimated values, SD of signed errors, and finite-B delta Monte Carlo SE `SD(e_b^2)/(2*sqrt(B)*RMSE)`, using scaled arithmetic. The stored lower/upper error-bar endpoints represent ±1 MCSE (lower clipped at zero), not a 95% CI. |
| [summarize_bootstrap_draws](../src/april_repro/clinical_bootstrap_statistics.py#L122), line 122 | Validates unique draw IDs, finite values, error consistency, and statuses. Only all planned complete draws yield `primary_metrics`; partial valid-draw summaries remain diagnostic. Failed/pending IDs are retained. |
| [clinical_dmplus_bootstrap_statistics._test](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L73), line 73 | Calls `scipy.stats.ttest_rel` on paired **squared errors**, two-sided, after common numerical scaling. Positive t favors DM+. All-zero differences give t=0/p=1; constant nonzero differences are explicitly degenerate. No multiple-testing adjustment. |
| [clinical_dmplus_bootstrap_statistics._metrics](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L113), line 113 | Combines each method's RMSE/MCSE, RMSE gain, squared-error gain, paired t-test, and the 2.5/50/97.5 percentiles of `abs(e_DM)-abs(e_DMplus)` using linear interpolation. |
| [summarize_paired_bootstrap_draws](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L171), line 171 | Pairs by integer draw ID, never by list order. Requires exact paired proxy values and compatible metadata. Missing/failed pairs stay in the planned denominator. Complete coverage is required for primary statistics. |
| [_full_point](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L152), line 152 | Separately reports the full-data, non-bootstrap point errors and their absolute-error gain; this is not the bootstrap RMSE. |

The paired t-test is a conditional Monte Carlo comparison for fixed data/labels, not a test using 500 independent new clinical cohorts. The absolute-error-gain percentile interval is not a confidence interval for the RMSE difference. These meanings are explicit in the code and should remain explicit in new reports.

### 7. Reward conversion and general arithmetic helpers

| Symbol and source | Responsibility |
|---|---|
| [reward_from_lab](../src/april_repro/rewards.py#L43), line 43 | Returns 1 inside the reference interval (K 3.5–4.5, Na 135–145); outside, returns `exp(-0.5*(distance/2.5)^2)`. Uses the adopted printed formula, with the original potassium-figure discrepancy documented in the module. |
| [bin_lab_value](../src/april_repro/rewards.py#L67), line 67 | Appendix-A categories, boundaries assigned to the class on the right: K `[3.2,5.0,6.0]`, Na `[118,135,152,169]`. These boundaries differ from reward reference intervals. |
| [direct_method](../src/april_repro/estimators.py#L43), line 43 | General equation `sum_x d0(x) sum_a pi(a\|x) Q(x,a)` from supplied matrices. Uniform event weights by default; explicitly supplied weights must already be probabilities. This function does not fit a model. Clinical evaluation kernels implement the same equation in batched NumPy rather than calling this helper. |
| [weighted_f1](../src/april_repro/metrics.py#L15), line 15 | Support-weighted multiclass F1 with fixed class count and explicit zero-division behavior. |
| [lab_weighted_f1](../src/april_repro/metrics.py#L58), line 58 | Bins observed/predicted lab values, then calls `weighted_f1`. Request failures and coverage accounting are handled by the caller, not by this numerical function. |
| [rmse](../src/april_repro/metrics.py#L89), line 89 | General RMSE against a scalar reference or matched reference sequence. The formal bootstrap summaries use the scaled arithmetic in `clinical_bootstrap_statistics`. |
| [bias](../src/april_repro/metrics.py#L98), line 98 | Mean signed error, estimate minus reference. |
| [marginal_entropy](../src/april_repro/metrics.py#L104), line 104 | Natural-log marginal entropy from nonnegative action counts. Its existence does not mean the paper's multi-source/entropy experiment has been completed; it does not measure annotation accuracy or conditional coverage. |

For low-level validation, `clinical_models.py` also contains `_numpy` (24), `_versions` (32), `_matrix` (39), `_vector` (58), `_actions` (69), `_json_copy` (79), `_initial_state` (311), and `RewardFit._base` (284). Dataset helpers are `_sha` (69), `_identifier` (97), `_event` (103), `_clock` (109), `_finite` (119), `_action` (143), and `_count` (149). Other helpers include `clinical_dmplus.file_sha256` (28), `clinical_dmplus_formal._id_set` (25), `clinical_bootstrap._usable_policy` (26), `_action_counts` (32), `_diagnostics` (36), the statistics modules' finite/mean/SD validators, `rewards._finite_real` (26) / `_validate_task` (38), `estimators._finite_matrix` (19) / `_validate_probabilities` (31), and `metrics._paired_errors` (70). These validate inputs or numerics; they are not separate learned models.

### 8. Where to implement a new method

| Proposed change | Relevant baseline to study | Recommended extension boundary |
|---|---|---|
| Confidence weighting, annotation weighting, or a robust/DRO reward fit | `fit_augmented_reward` (point) and `fit_paired_augmented_reward` (bootstrap) | Add a new module/fitter and its own versioned configuration. Keep the baseline OLS functions intact. If the parameterization remains linear, a compatible reward predictor can expose `predict_action_values`; record the new objective and weights explicitly. Patient-bootstrap multiplicity and the new method's weights are different quantities. |
| A different reward architecture or context–action interaction | `RewardFit`, `fit_reward`, and the paired evaluation kernel | Implement a separate predictor/fit path, declare its action encoding and preprocessing, and evaluate under the same fixed policy, validation events, proxy, and draws. This changes the modeled reward function, not the label-generation model. |
| A different policy model | `fit_policy` and `PolicyFit.predict_proba` | Treat this as a distinct experiment: changing the target policy changes what is being evaluated. Recompute and pair all affected baselines rather than comparing with saved values from another policy. |
| A different annotation model, prompt, or reward mapping | Formal annotation provenance/prefix selection and `reward_from_lab` | Create new versioned label evidence and source bindings. Preserve the old cache; do not relabel a source or overwrite its rewards. Offline cached reproduction does not request new annotations. |
| A different uncertainty or hypothesis-test procedure | The two `clinical_*bootstrap_statistics.py` modules | Add a separate named statistic with its assumptions and denominator. Do not silently reinterpret existing fields or rename the absolute-gain interval as an RMSE CI. |

A minimal new-method driver should import the checkout package, load authorized local inputs read-only, select the declared case/budget, reuse original patient draws and target-policy/reference identities, fit the new method, and write a new method identifier and artifacts. Existing formal-source loaders require the original raw provenance chain; the portable bundle offers already verified caches through its own loader path. Decide explicitly which input contract the new driver supports.

Start with synthetic checks for the new objective, zero-weight/zero-augmentation behavior where applicable, patient multiplicity, and unchanged evaluation identities. Then perform a limited, clearly labeled clinical draw check before the full comparison. Do not require a genuinely new method's estimates to equal the old baseline; equality belongs to the baseline-replay validation. Retain failed draws, fixed requested-label denominators, patient separation, and the original zero-budget baseline as appropriate to the declared new experiment.
