# Execution entry points

[Back to the code navigation guide](CODE_GUIDE.md).


All paths below are relative to the `Healthcare-OPE` checkout unless stated otherwise. Use the pinned Python environment described in `docs/REPRODUCTION.md`.

| Goal | Entry point | Inputs | Work performed |
|---|---|---|---|
| Read existing results | PDFs and CSVs under `reports/` | Included in the checkout | No command needed |
| Redraw the two selected budget curves | `plot_results.py` | `reports/all-budget-curves/source-metrics.json` | Renders saved aggregate values; no fitting or statistical reconstruction |
| Check implementation with synthetic data | `python -m unittest discover -s tests -v`, with `PYTHONPATH=src` | Included synthetic fixtures | Runs tests; does not reproduce clinical results |
| Reconstruct the two frozen clinical baselines | `run_reproduction.py --mode cached` | The separately downloaded restricted bundle | Verifies source bindings and recomputes summaries from saved draws |
| Refit the selected clinical baselines | `run_reproduction.py --mode fresh` | The same complete restricted bundle | Refits DM+ on specified original draws, optionally also refitting DM and the target policy |
| Understand how the original experiments were produced | `scripts/run_clinical*.py` | Original private artifact layout and provenance | Historical experiment orchestration; these are not the portable bundle interface |
| Inspect the early protocol/database tooling | `src/april_repro/cli.py` | Original checkout configuration and, for DB commands, a configured database | Protocol auditing or database discovery; not the selected-baseline runner |

### Important: the portable runner imports the bundle's numerical code

`run_reproduction.py::execute()` verifies the code hashes in the bundle's `cases.json`, then inserts **`<package-root>/src`** into Python's import path. The numerical functions therefore come from the restricted bundle, not from the checkout's `src/` directory. Its historical manifest paths are provenance fields; the portable runner resolves its actual inputs inside the relocated bundle.

**Editing `Healthcare-OPE/src/` does not change the numerical implementation used by this frozen-baseline command.** Editing the bundle's bound source or manifests causes verification to fail. Use this runner to establish baseline reproduction. A new method needs a separate implementation and output location; this guide does not add such an entry point. The runner also checks fresh estimates against saved values with an absolute tolerance of `1e-12`, so it is not an unrestricted new-method trainer.

The portable cases are exactly:

- `sodium_gender_deepseek`
- `potassium_dosage_gpt4omini`
- `all`, which selects both of the above

The five-model aggregate reports do not imply that this portable runner can refit all five models or every task/split.

### Inspect an entry point without starting work

The following help commands parse arguments and exit before loading clinical data, fitting models, creating experiment output, querying PostgreSQL, or calling an LLM. `PYTHONDONTWRITEBYTECODE=1` also suppresses Python bytecode-cache writes. Historical clinical scripts import their numerical dependencies before parsing, so their help requires the installed dependencies.

```bash
PYTHONDONTWRITEBYTECODE=1 python run_reproduction.py --help
PYTHONDONTWRITEBYTECODE=1 python plot_results.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_baseline.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_bootstrap.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_dmplus.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_dmplus_formal.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_dmplus_bootstrap.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_dmplus_bootstrap_models.py --help
PYTHONDONTWRITEBYTECODE=1 python scripts/run_clinical_dmplus_bootstrap_budgets.py --help
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m april_repro --help
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python -m april_repro db profile --help
```

These are macOS/Linux shell commands. The portable runner imports `fcntl` for locking and does not run in native Windows Python; use a Linux environment such as WSL. `--help` also needs a supported OS for modules that import `fcntl`.

## Portable reproduction: modes and exact arguments

Both modes require the full restricted bundle, including its unmodified `cases.json`, numerical sources, features, annotation artifacts, fitted models, and draw records. A Git clone supplies none of those clinical inputs. Download the named Release attachment, not GitHub's automatic Source code archive. The English ZIP extracts to `APRIL_selected_baselines_20261023`, without `_English` in the directory name.

| Argument | Accepted value and default | Meaning |
|---|---|---|
| `--package-root` | Path; defaults to the directory containing `run_reproduction.py` | Root of the extracted bundle. Supply it explicitly when running from the code checkout. |
| `--index` | Relative path; default `cases.json` | Original bundle index. Not a parameter file to edit for a new method. |
| `--mode` | `cached` or `fresh`; default `cached` | Select reconstruction or fitting. |
| `--case` | The two case IDs above, or `all`; default `all` | Select one or both frozen cases. |
| `--budgets` | Comma-separated unique integers from `0,100,200,300,400,500` | Default: all six in cached mode, only `500` in fresh mode. Counts requested annotation prefixes, not guaranteed valid replies. |
| `--draws` | Comma-separated unique original IDs `0` through `499` | Fresh only. Default: `0`. This chooses original draws, not new random seeds. |
| `--full500` | Flag | Fresh only. Selects all 500 original draw IDs. Mutually exclusive with `--draws`. |
| `--refit-dm` | Flag | Fresh only. Also refits the original DM and target policy, including their preprocessing, before fitting DM+. |
| `--resume` | Flag | Fresh only. Requires the same explicit output directory and unchanged run plan, sources, settings, dependencies, and runtime. |
| `--output` | Path to a new output directory | Recommended explicitly outside the checkout and bundle inputs. If omitted, defaults to a timestamped directory under `<package-root>/results/`. Existing directories are rejected except with valid fresh resume. |

The following example assumes the checkout and extracted bundle are siblings:

```text
your-working-directory/
  Healthcare-OPE/
  APRIL_selected_baselines_20261023/
    cases.json
    verify_package.py
    src/
    data/
```

Run these from `Healthcare-OPE`, after environment setup. Use new output directory names for new runs.

```bash
# Verify the extracted bundle.
python ../APRIL_selected_baselines_20261023/verify_package.py

# Reconstruct both cases at all six budgets from saved draws.
python run_reproduction.py \
  --package-root ../APRIL_selected_baselines_20261023 \
  --mode cached --case all \
  --output ../april-results/cached-first

# Refit only DM+ for two original sodium draws at two budgets.
python run_reproduction.py \
  --package-root ../APRIL_selected_baselines_20261023 \
  --mode fresh --case sodium_gender_deepseek \
  --draws 0,7 --budgets 0,500 \
  --output ../april-results/na-fresh-first

# Also refit DM and the target policy for one original potassium draw.
python run_reproduction.py \
  --package-root ../APRIL_selected_baselines_20261023 \
  --mode fresh --case potassium_dosage_gpt4omini \
  --draws 0 --budgets 0,500 --refit-dm \
  --output ../april-results/k-refit-first
```

`cached` rebuilds the statistics from all 500 saved draws for each selected budget. It does not fit models. `fresh` reuses each original draw's saved DM, target policy, factual preprocessor, and patient multiplicities, then refits DM+ using the fixed annotation prefix. Adding `--refit-dm` also reconstructs the original DM and target policy and checks their numerical agreement before DM+. At budget zero, DM+ is the exact DM identity.

A small fresh check is labeled `partial_fresh_check_not_full500`. It does not produce a primary 500-draw RMSE. For a complete selected-budget rerun, replace `--draws ...` with `--full500`. For resumption, repeat the original fresh command with the same output and add `--resume`; do not combine portable `--resume` with the historical `--resume-directory` option.

The output includes `run-plan.json` and `summary.json`; fresh runs also write committed per-draw results/models under case and budget directories. Read `summary.json`'s `status` and budget summaries to distinguish a small check from a full run. All these operations are local: no new API calls or database queries. Fresh clinical outputs remain restricted data.

### Functions inside `run_reproduction.py`

| Function(s) | Responsibility |
|---|---|
| `main` | Defines arguments, parses them, and reports errors. |
| `execute` | Loads/verifies the index and pinned dependencies, selects bundle source imports, validates arguments, creates/locks the output, records the run plan, and dispatches cases. |
| `verify_sources`, `artifact` | Verify input manifests, model/task identity, source bindings, code versions, and declared feature/point outputs. |
| `read_draws` | Verify and load the 500 committed records and sidecars, including the original-DM pairing. |
| `prepare_case` | Recompute original DM and paired summaries, compare saved statistics, and check fixed-prefix accounting. |
| `full_point`, `zero_records` | Extract full-data point estimates; represent budget zero by the saved DM records. |
| `annotations_for` | Load the requested budget's verified annotation subset from the point artifact and map it to dataset rows. |
| `fresh_case` | Load the clinical dataset, recover original patient draws, optionally refit DM/target, fit DM+, check equivalence, and summarize selected results. |
| `commit_fit`, `read_fit` | Commit fresh result/model files atomically and verify them during resume. |
| `check_close`, `compare_tree` | Check finite numerical agreement and model-state structure. |
| `sha`, `verify`, `inside`, `load`, `save`, `numbers` | Hashing, bundle path containment, JSON I/O, and validated draw/budget lists. |

## Historical clinical scripts: source navigation, not the bundle interface

These scripts explain the original execution pipeline. They use checkout-oriented `ROOT`, original artifact-relative paths, source-code snapshots, and/or original provider-evidence chains. The portable package has a relocated `data/` layout and a selected subset of artifacts. Pointing a historical script at that package does not make it portable. Use `run_reproduction.py` for the delivered cases.

The clinical scripts themselves perform local model/statistical work and do not send new LLM requests. The formal scripts verify existing annotation evidence; that is different from generating annotations.

| Script | Role and useful functions | Actual CLI arguments | Original input/output assumptions |
|---|---|---|---|
| `scripts/run_clinical_baseline.py` | Full-data policy clones and OLS DM point baseline. `run`, `point_dm`, `score_policy`, `classification_report`, `validate_protocol`. | Required `--input-directory`. | Input under `artifacts/treatment-features/`; creates a new directory under `artifacts/clinical-baselines/`. No `--output-directory` or resume option. |
| `scripts/run_clinical_bootstrap.py` | Original 500-draw DM bootstrap. `run`, `commit_draw`, `read_committed`, `summarize_results`, `exclusive_run`. | Exactly one of `--input-directory` or `--resume-directory`; optional positive `--max-new-draws`. | Feature input under `artifacts/treatment-features/`; output/resume under `artifacts/clinical-bootstrap/`. There is no `--output-directory` option. |
| `scripts/run_clinical_dmplus.py` | Earlier pilot DM+ points from saved baselines and verified pilot receipts. `run`, `load_baseline`, `local_path`. | Required `--baseline-directory`, `--summary-directory`; optional `--output-directory`. | Baselines under `artifacts/clinical-baselines/`, summaries under `artifacts/llm-summaries/`, outputs under `artifacts/clinical-dmplus/`. This is the pilot path, not the formal five-model path. |
| `scripts/run_clinical_dmplus_formal.py` | Formal fixed-prefix DM+ points at budgets 0–500 for one annotation model. `run`, plus imported `load_model_evidence` and `select_prefix`. | Required `--plan-directory`, `--run-directory`, `--baseline-directory` (repeatable), `--output-directory`; `--model-key` defaults to `deepseek`. | Requires original formal request plan/run evidence and complete point baselines. Feature paths are recovered from original baseline manifests under checkout `ROOT`. |
| `scripts/run_clinical_dmplus_bootstrap.py` | Original DeepSeek-only 500-budget paired bootstrap. `_run`, `load_dm_source`, `load_point_source`, `read_committed`, `commit_draw`, `summarize`. | New run: `--dm-bootstrap-directory`, `--point-directory`, `--output-directory`. Resume: `--resume-directory`. Optional positive `--max-new-draws`. | Fixed DeepSeek/500 configuration; complete original DM and formal point sources. Output under `artifacts/clinical-dmplus-bootstrap/`. |
| `scripts/run_clinical_dmplus_bootstrap_models.py` | Same paired-bootstrap core with explicit model selection. `_run`, `validate_model_key`, source loaders, commit/resume helpers. | Same arguments as preceding row, plus required `--model-key` for a new run. | Model choices: `gpt-4o-mini`, `o3-mini`, `kimi`, `deepseek`, `qwen`; fixed budget 500; output under `artifacts/clinical-dmplus-bootstrap/`. |
| `scripts/run_clinical_dmplus_bootstrap_budgets.py` | Same core for a specified nonzero annotation prefix. `_run`, `validate_annotation_budget`, `source_path`, source loaders, commit/resume helpers. | Same source/output/resume/draw-limit arguments, plus `--model-key` and `--annotation-budget` for a new run. Also exposes internal `--verification-root`. | Allowed budgets are **100, 200, 300, 400, 500**. Output under `artifacts/clinical-dmplus-budget-bootstrap/`; directory name must end with `-<budget>`. |

For the three paired-bootstrap scripts, resume takes `--resume-directory` and optionally `--max-new-draws`; do not repeat new-run source/output/model/budget arguments. Saved provenance supplies these values. `--max-new-draws` limits work in that invocation; it does not change the planned 500 draws per estimable split.

The budget script's old module/help text mentions zero, but its actual parser and configuration accept only 100–500. Budget zero is reused from original DM; the portable runner does accept `--budgets 0`. The internal `--verification-root` is for bounded checks beneath `/private/tmp` and requires `--max-new-draws`. Its `APRIL_BUDGET_BOOTSTRAP_PROJECT_ROOT` environment override selects an original project root for verification; it does not replace the portable package adapter.

### Configuration files and their consumers

| File | Consumer and purpose |
|---|---|
| `config/clinical-baseline.toml` | `run_clinical_baseline.py` and the DM bootstrap's model-protocol validation: preprocessing, logistic policy, OLS reward, and point evaluation settings. |
| `config/clinical-bootstrap.toml` | `run_clinical_bootstrap.py`: original patient populations, seed, 500 draws, refits, and DM statistics. |
| `config/clinical-dmplus-bootstrap.toml` | `run_clinical_dmplus_bootstrap.py`: DeepSeek/500 paired-bootstrap protocol. |
| `config/clinical-dmplus-bootstrap-models.toml` | `run_clinical_dmplus_bootstrap_models.py`: allowed model keys, fixed budget 500, unchanged paired protocol. |
| `config/clinical-dmplus-bootstrap-budgets.toml` | `run_clinical_dmplus_bootstrap_budgets.py`: nonzero budget choices and separate output namespace. |
| `requirements-g3.lock` | Pinned numerical versions checked by the clinical runners. |
| `requirements-plot.txt` | Matplotlib dependency for `plot_results.py`; it does not define the scientific model. |

These files record fixed implementations, and the historical scripts validate their settings. They are not an unrestricted hyperparameter tuning interface. Some old text such as “pending” describes the stage when that specific configuration was recorded; consult completed reports/manifests for current progress. The portable runner derives its bindings from the original bundle index/manifests rather than treating the checkout configuration as a live override.

## The early `april_repro` CLI

`src/april_repro/__main__.py` calls `src/april_repro/cli.py::main()`. From a checkout, inspect it with `PYTHONPATH=src python -m april_repro --help`. The installed `april-repro` console command points to the same function, but installing requirements alone does not install that console command.

The optional global `--project-root PATH` precedes the subcommand. It expects `config/protocol.toml`. Available operations are:

| Command after `python -m april_repro` | What it actually does |
|---|---|
| `doctor` | Checks early protocol/preregistration files and local environment; may call `psql --version` but does not connect to the database. |
| `protocol check` | Validates the early draft specification and preregistration records. `--require-frozen` additionally requires a frozen status. |
| `db check` | Runs a configured read-only database identity query and writes local evidence artifacts. |
| `db inspect` | Runs configured read-only database metadata queries and writes local evidence artifacts. |
| `db profile` | Runs registered aggregate/dictionary profiling queries; repeat `--query NAME` to select queries. Without it, the registered set is selected. |

All three `db` operations accept `--timeout-ms` from 100 through 120000, default 10000. They are actual database operations when run without `--help`. The database connection is unnecessary for portable replay/refitting.

`doctor` and `protocol check` belong to the original extraction/audit workflow. They expect historical preregistration documents and artifacts omitted from this distribution, so they can fail in this trimmed checkout. They are not acceptance checks that a new member must pass before using the documented portable bundle. Use the shipped synthetic tests and bundle verification for the delivered workflow.

## Follow execution into the numerical functions

| Calculation | Source entry points |
|---|---|
| Load and validate clinical feature/split/outcome artifacts | `src/april_repro/clinical_dataset.py::load_clinical_dataset`, `ClinicalDataset` |
| Fit preprocessing and original models | `src/april_repro/clinical_models.py::fit_preprocessor`, `fit_policy`, `fit_reward`; saved model interfaces `PolicyFit`, `RewardFit` |
| Read/select formal annotation evidence | `src/april_repro/clinical_dmplus_formal.py::load_model_evidence`, `select_prefix` |
| Fit/evaluate the full-data augmented reward model | `src/april_repro/clinical_dmplus.py::fit_augmented_reward`, `evaluate_pair`, `verify_saved_dm` |
| Define patient populations and original resampling | `src/april_repro/cluster_bootstrap.py::build_cluster_population`, `ClusterPopulation.draw` |
| Refit an original DM draw | `src/april_repro/clinical_bootstrap.py::run_dm_draw` |
| Replay a draw and fit DM+ with matched multiplicities | `src/april_repro/clinical_dmplus_bootstrap.py::replay_original_draw`, `annotation_multiplicities`, `fit_paired_augmented_reward`, `run_paired_draw` |
| Summarize DM draws | `src/april_repro/clinical_bootstrap_statistics.py::summarize_bootstrap_draws` |
| Summarize paired DM/DM+ results | `src/april_repro/clinical_dmplus_bootstrap_statistics.py::summarize_paired_bootstrap_draws`; `_test` computes the conditional squared-error test. |

Search these symbols in an editor, or use `rg` from the checkout root:

```bash
rg -n '^def (main|execute|fresh_case|prepare_case)\(' run_reproduction.py
rg -n '^def (fit_policy|fit_reward|fit_preprocessor)\(' src/april_repro/clinical_models.py
rg -n '^def (run_dm_draw|run_paired_draw|summarize_paired_bootstrap_draws)\(' src/april_repro
rg -n 'add_argument|PROTOCOL =|CODE_PATHS =' scripts/run_clinical*.py
```

The reported paired test uses differences of per-draw squared errors. It compares a conditional Monte Carlo distribution, not 500 independent patient cohorts or a recovered implementation of the paper's undisclosed RMSE-pair construction. Keep this distinction when connecting the runner to the report tables.
