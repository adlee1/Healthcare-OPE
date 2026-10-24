# Reproduction guide

There are two separate workflows: data-free inspection of published aggregate results, and clinical baseline reproduction using an authorized restricted local bundle. A plain Git clone supports the first workflow only.

## Environment and data-free checks

Use Python 3.12. Numerical dependencies are pinned in `requirements-g3.lock`: NumPy 2.2.6, SciPy 1.15.3, scikit-learn 1.7.2, joblib 1.5.2, and threadpoolctl 3.6.0. Plotting uses Matplotlib 3.9.2, pinned in `requirements-plot.txt`. The portable runner uses a POSIX file lock and supports macOS/Linux.

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-g3.lock
python -m pip install -r requirements-plot.txt
PYTHONPATH=src python -m unittest discover -s tests -v
python plot_results.py --output outputs/figures
```

The tests use synthetic inputs. Plotting reads shipped aggregate metrics and writes PNG, PDF, and SVG figures. Neither operation requires clinical data or credentials. Dependency installation may access a package index; for an entirely offline environment, prepare compatible wheels in advance. The reproduction runner itself makes no network or database calls.

## Attach a restricted local bundle

First follow [DATA_ACCESS.md](DATA_ACCESS.md). Keep the authorized bundle and its outputs outside the Git checkout. Set the following variables to existing approved local storage locations:

```bash
APRIL_BUNDLE="/approved/storage/APRIL_selected_baselines_20261023"
APRIL_RESULTS="/approved/storage/Healthcare-OPE-results"
```

The paths above illustrate the required locations; they are not download destinations. A valid bundle contains its original `cases.json`, unchanged numerical sources, and the bound data artifacts. The original `cases.json` is not distributed in the GitHub repository; a data-free case description cannot replace that index or the missing inputs.

The available case IDs are:

- `sodium_gender_deepseek`
- `potassium_dosage_gpt4omini`

Commands below are issued from the repository root. `--package-root` selects the external bundle; `--output` selects a new external output directory. Do not modify the bundle's original manifests to change historical paths.

## Reconstruct cached statistics

```bash
python run_reproduction.py \
  --package-root "$APRIL_BUNDLE" \
  --mode cached --case all \
  --output "$APRIL_RESULTS/cached-rebuilt"
```

This verifies the selected source bindings and rebuilds all six request-budget summaries: 0, 100, 200, 300, 400, and 500. Each summary uses the original 500 paired patient-bootstrap draws. Budget zero is the exact DM identity. This is a statistical reconstruction from stored draws, not model retraining, and it still requires restricted inputs.

## Refit a small baseline check

By default, fresh mode refits DM+ while reusing the original draw's fitted DM, target policy, factual preprocessor, and patient counts:

```bash
python run_reproduction.py \
  --package-root "$APRIL_BUNDLE" \
  --mode fresh --case sodium_gender_deepseek \
  --draws 0,7 --budgets 0,100,200,300,400,500 \
  --output "$APRIL_RESULTS/na-fresh-check"
```

To also retrain the original DM and target policy from the packaged clinical features:

```bash
python run_reproduction.py \
  --package-root "$APRIL_BUNDLE" \
  --mode fresh --case potassium_dosage_gpt4omini \
  --draws 0 --budgets 0,500 --refit-dm \
  --output "$APRIL_RESULTS/k-model-refit-check"
```

`--refit-dm` invokes the original numerical functions and verifies the original patient draws, model state, and estimates before refitting DM+. Fixed annotation prefixes, invalid-label handling, patient selection, and the bootstrap seed are unchanged.

A limited check is labeled `partial_fresh_check_not_full500`. It retains a planned denominator of 500, sets `primary_metrics` to null, and reports any available calculations as diagnostic only. Completing the requested small check does not complete the 500-draw experiment.

## Run or resume all 500 draws

```bash
python run_reproduction.py \
  --package-root "$APRIL_BUNDLE" \
  --mode fresh --case potassium_dosage_gpt4omini \
  --budgets 500 --full500 \
  --output "$APRIL_RESULTS/k-full500"
```

Add `--refit-dm` to retrain both original models for every draw. Select all six budgets explicitly to rerun the complete curve. Cases run sequentially; potassium requires substantially more memory and time than sodium. Without explicit draw options, fresh mode checks only draw 0 at budget 500.

After interruption, repeat the same command with `--resume`:

```bash
python run_reproduction.py \
  --package-root "$APRIL_BUNDLE" \
  --mode fresh --case potassium_dosage_gpt4omini \
  --budgets 500 --full500 \
  --output "$APRIL_RESULTS/k-full500" --resume
```

The run plan binds the source index, runner, dependencies, runtime, case, budgets, draw IDs, and refit settings. Resume validates committed result/model hashes and skips complete fits. It rejects changed settings or corrupted outputs and does not overwrite original baselines. Only complete coverage of all 500 draw IDs produces primary bootstrap statistics.

## Numerical agreement and future methods

The baseline runner checks fresh estimates against the saved baseline with an absolute tolerance of `1e-12`. Pinned package versions do not guarantee identical floating-point behavior across all BLAS libraries and architectures. Report a mismatch; do not silently loosen the tolerance or rewrite the original results.

This equality check validates baseline reproduction. A new method should use a separately versioned implementation and new outputs; it should not be required to reproduce the baseline numerically. Preserve patient separation, reference definitions, annotation budgets, and source provenance when making comparisons. The selected cases were chosen post hoc and need an evaluation strategy that accounts for that selection. Statistical interpretation is documented in [METHODS.md](METHODS.md).
