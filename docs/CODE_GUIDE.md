# Code navigation and execution guide

This is the starting point for collaborators who want to read the implementation, locate models, run baseline code, or develop a new method. For installation and data download, use [REPRODUCTION.md](REPRODUCTION.md).

## Read these files first

| Question | File and symbols to open |
|---|---|
| Where are the locally fitted models? | [clinical_models.py](../src/april_repro/clinical_models.py): `Preprocessor`, `PolicyFit`, `RewardFit`, `fit_policy`, `fit_reward` |
| Where is ordinary DM fitted for a bootstrap draw? | [clinical_bootstrap.py](../src/april_repro/clinical_bootstrap.py): `run_dm_draw` |
| Where does DM+ add LLM labels and fit its reward model? | [clinical_dmplus.py](../src/april_repro/clinical_dmplus.py): `fit_augmented_reward` for the point estimate; [clinical_dmplus_bootstrap.py](../src/april_repro/clinical_dmplus_bootstrap.py): `fit_paired_augmented_reward`, `run_paired_draw` for bootstrap |
| Where are the five LLMs configured? | [llm_five_requests.py](../src/april_repro/llm_five_requests.py) and [llm-five-models-qwen-domestic.toml](../config/llm-five-models-qwen-domestic.toml); see [LLM_CODE.md](LLM_CODE.md) for registry variants and request flow |
| Where are RMSE and t-test calculations? | [clinical_bootstrap_statistics.py](../src/april_repro/clinical_bootstrap_statistics.py): `_metrics`, `summarize_bootstrap_draws`; [clinical_dmplus_bootstrap_statistics.py](../src/april_repro/clinical_dmplus_bootstrap_statistics.py): `_test`, `_metrics`, `summarize_paired_bootstrap_draws` |
| Where does patient resampling happen? | [cluster_bootstrap.py](../src/april_repro/cluster_bootstrap.py): `ClusterPopulation`, `ClusterDraw`, `build_cluster_population` |
| Where are data loaded and split? | [clinical_dataset.py](../src/april_repro/clinical_dataset.py): `load_clinical_dataset`, `ClinicalDataset.mask`; [cohort_patient_splits.py](../src/april_repro/cohort_patient_splits.py): `build_patient_cohort_splits` |
| Where is the lab-to-reward formula? | [rewards.py](../src/april_repro/rewards.py): `reward_from_lab`; `bin_lab_value` defines the separate F1 bins |
| Which file do I run for the two packaged baselines? | [run_reproduction.py](../run_reproduction.py): `main`, `execute`, `fresh_case` |
| How do I locate every function, including helpers and tests? | [FUNCTION_INDEX.md](FUNCTION_INDEX.md): source links, signatures, classes, methods, nested functions, and existing docstrings |

Detailed guides: [model and evaluation functions](MODEL_CODE.md), [execution entry points](RUNNERS.md), [LLM configuration and adapters](LLM_CODE.md).

## What the different models mean

| Name | Implementation | Output |
|---|---|---|
| Target/behavior policy | `PolicyFit`, trained by `fit_policy` using logistic regression with explicit constant/class-frequency fallbacks | An action-probability vector for a clinical context |
| DM reward model | `RewardFit`, trained by `fit_reward` using ordinary least squares on factual rows | Predicted reward for a context/action pair |
| DM+ reward model | The same `RewardFit` representation; augmented fitting adds valid counterfactual rows and retains factual preprocessing | Predicted reward for the same action space |
| GPT-4o-mini, o3-mini, DeepSeek, Qwen, Kimi | External APIs accessed through shared request and transport code | A predicted post-treatment lab value, later converted to a reward |

There are no local weights or separate neural-network training files for those five LLMs. Their labels feed the same DM+ fitting code, selected by `model_key`. The current repository does not implement a DRO method; it is a proposed extension.

## Which program to run

Run commands from the `Healthcare-OPE` checkout after activating the documented Python 3.12 environment. The examples assume this directory layout:

```text
work/
  Healthcare-OPE/                         # Git checkout
  APRIL_selected_baselines_20261023/      # Extracted private Release bundle
    cases.json
    src/april_repro/
    data/
  april-results/                         # New outputs
```

The download is named `APRIL_selected_baselines_20261023_English.zip`, but its extracted directory has no `_English` suffix.

| Goal | Entry point | What runs |
|---|---|---|
| Recalculate the saved 500-draw statistics | `run_reproduction.py --mode cached` | Reads saved original/augmented draws and rebuilds summaries; does not fit models |
| Refit DM+ on a small selected draw set | `run_reproduction.py --mode fresh` | Reuses saved DM and target policy, then refits DM+ using the same cached annotations |
| Also refit DM and the target policy | Add `--refit-dm` to fresh mode | Calls `run_dm_draw` before `run_paired_draw` and verifies agreement with the original baseline |
| Refit every original draw | Add `--full500` to fresh mode | Runs draw IDs 0–499 for the requested case/budgets |
| Study original experiment entry scripts | `scripts/run_clinical_*.py` | See [RUNNERS.md](RUNNERS.md) for each script's inputs and historical-directory dependencies |
| Check implementation on synthetic examples | `PYTHONPATH=src python -m unittest discover -s tests -v` | Runs tests against checkout source |
| Draw existing aggregate results | `python plot_results.py --output outputs/figures` | Renders shipped metrics; does not train or resample |

First inspect available options:

```bash
python run_reproduction.py --help
```

Reconstruct both selected baselines from saved draws:

```bash
python run_reproduction.py \
  --package-root ../APRIL_selected_baselines_20261023 \
  --mode cached --case all \
  --output ../april-results/cached-first
```

Run one complete model-refitting check for the sodium gender / DeepSeek baseline:

```bash
python run_reproduction.py \
  --package-root ../APRIL_selected_baselines_20261023 \
  --mode fresh --case sodium_gender_deepseek \
  --draws 0 --budgets 0,500 --refit-dm \
  --output ../april-results/na-model-check
```

For the potassium dosage / GPT-4o-mini baseline, use `--case potassium_dosage_gpt4omini` and a different output directory. Each output directory must be new unless explicitly resuming. A one-draw check is not a completed 500-draw result. These commands do not generate new LLM labels or query PostgreSQL.

## Follow the function calls

```text
run_reproduction.py: main()
  execute()
    verify package index, source hashes, dependencies
    prepare_case()
      locate features, point estimates, saved DM and DM+ draws
      summarize_paired_bootstrap_draws()              [cache verification in both modes]
    fresh_case()                                     [fresh mode]
      load_clinical_dataset()
      build_cluster_population()
      annotations_for() -> verified cached Counterfactual records
      run_dm_draw()                                 [only --refit-dm]
        fit_policy() -> PolicyFit
        fit_reward() -> RewardFit
      run_paired_draw()
        replay_original_draw()
        annotation_multiplicities()
        fit_paired_augmented_reward() -> RewardFit
        _evaluate()
      summarize_paired_bootstrap_draws()
        RMSE, Monte Carlo SE, paired squared-error t-test, gain percentiles
```

**Source selection matters:** `execute()` inserts the extracted bundle's `src/` at the front of Python's import path. These baseline commands execute frozen bundle code. Changing `Healthcare-OPE/src/` does not change their numerical implementation. The package's hashes and equality checks deliberately preserve the original baseline.

## Where fitted model files are stored

The following paths are relative to the extracted data bundle, not the Git checkout:

| Artifact | Example location |
|---|---|
| Data/source index for both selected cases | `cases.json` |
| Sodium clinical features and fixed splits | `data/features/sodium/` |
| Potassium clinical features and fixed splits | `data/features/potassium/` |
| Original sodium DM and target policy for draw 0 | `data/dm/sodium/gender/draw-000/models.json` |
| Original potassium DM and target policy for draw 0 | `data/dm/potassium/dosage/draw-000/models.json` |
| Sodium / DeepSeek DM+ at the 500-request budget | `data/dmplus/sodium_gender_deepseek/gender/draw-000/models.json` |
| Potassium / GPT-4o-mini DM+ at the 500-request budget | `data/dmplus/potassium_dosage_gpt4omini/dosage/draw-000/models.json` |
| Other request budgets for the selected cases | `data/budget_dmplus/<case>/<budget>/` |
| Full-data point fits and cached annotation artifacts | `data/points/<case>/` |

DM bootstrap model files contain `target_policy` and `reward_model`; DM+ bootstrap files contain `reward_model_plus` and metadata. These are JSON model states with coefficients and preprocessing, rather than `.pt` neural-network checkpoints. `PolicyFit.from_dict` and `RewardFit.from_dict` restore them. Use `cases.json` for authoritative source paths and hashes instead of rewriting old manifest paths.

## How to start a new method

Study `fit_augmented_reward` and `fit_paired_augmented_reward` first if the intended change is annotation weighting or a robust reward objective. Study `RewardFit.predict_action_values` to preserve the evaluator's prediction interface.

Create a separately named method module and entry script that imports the checkout package, reads the authorized bundle as input, and writes new outputs. It should evaluate DM, DM+, and the new method with the same declared policy, patient splits, draw IDs, annotation budget, and reference definition. The detailed extension table is in [MODEL_CODE.md](MODEL_CODE.md#8-where-to-implement-a-new-method).

Do not use the frozen baseline runner as an unversioned experimental driver: it is designed to reject a changed numerical baseline. Tests invoked with `PYTHONPATH=src` do use checkout source. To confirm the import location in a fresh development process:

```bash
PYTHONPATH=src python -c "import april_repro.clinical_models as m; print(m.__file__)"
```

## Historical extraction and support modules

The larger source tree also preserves cohort construction and evidence-checking code. These files explain how the original artifacts were built; they are not alternative learned models.

| Area | Files to inspect |
|---|---|
| Pretreatment feature assembly | `decision_features.py`, `config/decision-features.toml` |
| Treatment decisions and sodium infusion episodes | `treatment_decisions.py`, `decision_opportunities.py`, `sodium_episodes.py` |
| Patient roles and train/validation assignment | `cohort_patient_splits.py`, `cohort_splits.py` |
| Outcome and unit rules | `outcomes.py`, `rewards.py`, `units.py` |
| Database/query definitions | `database.py`, `sql/`, `config/profile_queries.toml` |
| Extraction provenance and adjudication | `query202_*.py`, `product_*`, `route_*`, `*_preregistration.py`, `*_audit.py` |
| Numerical examples and regression checks | `tests/test_clinical_models.py`, `test_clinical_dmplus.py`, `test_cluster_bootstrap.py`, `test_clinical_dmplus_bootstrap.py`, `test_clinical_dmplus_bootstrap_statistics.py`, `test_run_reproduction.py` |

The project-wide CLI (`PYTHONPATH=src python -m april_repro --help`) exposes historical audit/database commands. It is not the portable clinical reproduction or live five-model annotation entry point. See the exact scope in [RUNNERS.md](RUNNERS.md).
