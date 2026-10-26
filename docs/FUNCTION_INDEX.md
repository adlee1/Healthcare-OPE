# Python function and class index

Start with [CODE_GUIDE.md](CODE_GUIDE.md) for model roles, execution entry points, and the development workflow.

This generated index covers **112 Python files** and **1931 named definitions** in root scripts, `scripts/`, `src/`, and `tests/`.

Every named function, method, nested function, and class is included. Click a source line to read its implementation. The descriptions below are existing source docstrings, not inferred documentation; a blank description means no docstring is present. Anonymous lambdas and dynamically assigned callables are outside this static index.

Regenerate after source edits with `python scripts/generate_code_index.py`. The generator parses syntax only: it does not import project modules, load clinical data, train models, or call APIs.

## File navigation

| File | Definitions |
|---|---:|
| [plot_results.py](#module-13a578d39606) | 1 |
| [run_reproduction.py](#module-43dd4fabe3da) | 20 |
| [scripts/check_repository_boundary.py](#module-f4eaec313b57) | 5 |
| [scripts/generate_code_index.py](#module-f2cefc04b3de) | 5 |
| [scripts/run_clinical_baseline.py](#module-35194e4c54ad) | 11 |
| [scripts/run_clinical_bootstrap.py](#module-914225b0c929) | 10 |
| [scripts/run_clinical_dmplus.py](#module-2324533abe49) | 5 |
| [scripts/run_clinical_dmplus_bootstrap.py](#module-ad0ecf3c30c5) | 10 |
| [scripts/run_clinical_dmplus_bootstrap_budgets.py](#module-64fb5915b538) | 13 |
| [scripts/run_clinical_dmplus_bootstrap_models.py](#module-8b391cd054d8) | 11 |
| [scripts/run_clinical_dmplus_formal.py](#module-7858272039e0) | 2 |
| [scripts/summarize_five_llm_runs.py](#module-50d7c6de8573) | 1 |
| [scripts/summarize_formal_llm_run.py](#module-01beac891d00) | 1 |
| [src/april_repro/__init__.py](#module-053a77878e7e) | 0 |
| [src/april_repro/__main__.py](#module-3877859ece09) | 0 |
| [src/april_repro/cli.py](#module-5b21272378ec) | 8 |
| [src/april_repro/clinical_bootstrap.py](#module-986af6fec78e) | 5 |
| [src/april_repro/clinical_bootstrap_statistics.py](#module-310e99800810) | 5 |
| [src/april_repro/clinical_dataset.py](#module-12cd3f11d1c3) | 16 |
| [src/april_repro/clinical_dmplus.py](#module-e441a7c7e804) | 8 |
| [src/april_repro/clinical_dmplus_bootstrap.py](#module-fb6d3745e499) | 5 |
| [src/april_repro/clinical_dmplus_bootstrap_statistics.py](#module-9274e63d0bca) | 7 |
| [src/april_repro/clinical_dmplus_formal.py](#module-e11f3ddc0558) | 4 |
| [src/april_repro/clinical_models.py](#module-417bc28543c4) | 35 |
| [src/april_repro/cluster_bootstrap.py](#module-382d1440f0b3) | 12 |
| [src/april_repro/cohort_patient_splits.py](#module-ecbf39339f2e) | 4 |
| [src/april_repro/cohort_splits.py](#module-f69dd38e736c) | 7 |
| [src/april_repro/database.py](#module-a47c0ca907b8) | 11 |
| [src/april_repro/decision_features.py](#module-4caccf92a702) | 6 |
| [src/april_repro/decision_opportunities.py](#module-0083d978557e) | 10 |
| [src/april_repro/estimators.py](#module-1ecee1237dcb) | 3 |
| [src/april_repro/evidence.py](#module-713cf24c3006) | 3 |
| [src/april_repro/full_decisions.py](#module-26b5dde6800b) | 8 |
| [src/april_repro/full_vocabulary_audit.py](#module-168653ace03c) | 23 |
| [src/april_repro/full_vocabulary_discovery.py](#module-0d4381fe7079) | 26 |
| [src/april_repro/linear_training_candidate.py](#module-6bf4b49657a8) | 12 |
| [src/april_repro/llm_credentials.py](#module-89f15ee96967) | 1 |
| [src/april_repro/llm_five_packet.py](#module-02e1efc2bbf5) | 10 |
| [src/april_repro/llm_five_requests.py](#module-608a4ffa1e9b) | 10 |
| [src/april_repro/llm_formal_plan.py](#module-daa8c4217aac) | 6 |
| [src/april_repro/llm_formal_recovery.py](#module-a9f9c1822e86) | 11 |
| [src/april_repro/llm_formal_recovery_v2.py](#module-2bca12e30c6b) | 11 |
| [src/april_repro/llm_formal_run.py](#module-0aa74a2178bd) | 21 |
| [src/april_repro/llm_formal_summary.py](#module-1293ad6e43cc) | 6 |
| [src/april_repro/llm_packet.py](#module-2bc9a927608a) | 10 |
| [src/april_repro/llm_predictions.py](#module-ca6695d905df) | 12 |
| [src/april_repro/llm_receipts.py](#module-c325abcc9d9c) | 10 |
| [src/april_repro/llm_requests.py](#module-7685f35bf1bc) | 9 |
| [src/april_repro/llm_retries.py](#module-6e5d08e5ef8e) | 3 |
| [src/april_repro/llm_run_summary.py](#module-e566e92033ec) | 10 |
| [src/april_repro/llm_transport.py](#module-2ca648dcc141) | 6 |
| [src/april_repro/mapping_preflight.py](#module-2c071c4cc67b) | 27 |
| [src/april_repro/mapping_preflight_audit.py](#module-11bd06e9a8c6) | 30 |
| [src/april_repro/metrics.py](#module-9e47e978bedf) | 6 |
| [src/april_repro/outcomes.py](#module-970d896b54ed) | 10 |
| [src/april_repro/paired_training_candidate.py](#module-9df8b81c9ad0) | 12 |
| [src/april_repro/paper_alignment.py](#module-c8930f1332a5) | 3 |
| [src/april_repro/preregistration.py](#module-69b6401a28a8) | 19 |
| [src/april_repro/product_mapping_contract.py](#module-4ee0e1ad8121) | 8 |
| [src/april_repro/product_review_ledger.py](#module-276293bd2195) | 33 |
| [src/april_repro/product_review_ledger_audit.py](#module-25e95d1b00a7) | 20 |
| [src/april_repro/profiling.py](#module-d0f95cc886b4) | 5 |
| [src/april_repro/query202_adjudication_input.py](#module-1ab099914877) | 62 |
| [src/april_repro/query202_adjudication_input_audit.py](#module-dadd82854641) | 64 |
| [src/april_repro/query202_adjudication_input_preregistration.py](#module-64eb239fa72d) | 12 |
| [src/april_repro/query202_contract.py](#module-6305b8e29b5a) | 4 |
| [src/april_repro/query202_human_adjudication.py](#module-e35adadd0639) | 92 |
| [src/april_repro/query202_human_adjudication_audit.py](#module-0c6d2b46e023) | 94 |
| [src/april_repro/query202_human_adjudication_finalize.py](#module-d1bc69c282be) | 56 |
| [src/april_repro/query202_human_adjudication_preregistration.py](#module-29f5b6dd9a1f) | 43 |
| [src/april_repro/query202_human_adjudication_writer.py](#module-3c937a2924e2) | 44 |
| [src/april_repro/query202_ndc_evidence_mode_preregistration.py](#module-8e0fa73d6670) | 21 |
| [src/april_repro/query202_pre_adjudication.py](#module-8ed920062a25) | 81 |
| [src/april_repro/query202_pre_adjudication_audit.py](#module-7a611285d725) | 57 |
| [src/april_repro/query202_pre_adjudication_preregistration_v2.py](#module-570ac2027d54) | 29 |
| [src/april_repro/query202_preadjudication_sql_v2.py](#module-4809a5f369fb) | 11 |
| [src/april_repro/query202_preregistration.py](#module-7752fb27fa99) | 21 |
| [src/april_repro/query202_readonly_explain_attestation.py](#module-4dc43ccab11c) | 19 |
| [src/april_repro/rewards.py](#module-563e83980328) | 4 |
| [src/april_repro/route_adjudication.py](#module-2928af8fe7fc) | 28 |
| [src/april_repro/route_adjudication_audit.py](#module-fa9118784b62) | 25 |
| [src/april_repro/route_adjudication_preregistration.py](#module-a0ad20cd70f0) | 4 |
| [src/april_repro/sharded_source_closure.py](#module-22acc79fcaef) | 28 |
| [src/april_repro/sodium_episodes.py](#module-0ab5ba222660) | 7 |
| [src/april_repro/source_closure_merge.py](#module-3367d4dcac3a) | 48 |
| [src/april_repro/staged_source_closure.py](#module-b4d49fe50ec6) | 31 |
| [src/april_repro/treatment_decisions.py](#module-dbc3e895c1bc) | 12 |
| [src/april_repro/units.py](#module-8608c525021e) | 1 |
| [tests/__init__.py](#module-001e61d97d9d) | 0 |
| [tests/test_clinical_baseline.py](#module-042e77e91561) | 21 |
| [tests/test_clinical_bootstrap.py](#module-7eaa37e3d998) | 25 |
| [tests/test_clinical_bootstrap_runner.py](#module-23967c776c01) | 13 |
| [tests/test_clinical_bootstrap_statistics.py](#module-d35afe662435) | 22 |
| [tests/test_clinical_dataset.py](#module-f0bcca423fb6) | 31 |
| [tests/test_clinical_dmplus.py](#module-0e9d7257b534) | 17 |
| [tests/test_clinical_dmplus_bootstrap.py](#module-cd21bc5f39d5) | 15 |
| [tests/test_clinical_dmplus_bootstrap_budgets_runner.py](#module-fee26819572e) | 30 |
| [tests/test_clinical_dmplus_bootstrap_models_runner.py](#module-f0caf5012282) | 21 |
| [tests/test_clinical_dmplus_bootstrap_runner.py](#module-bc6ceaaef39c) | 13 |
| [tests/test_clinical_dmplus_bootstrap_statistics.py](#module-b7094df15a13) | 22 |
| [tests/test_clinical_dmplus_formal.py](#module-e12f01dc791f) | 20 |
| [tests/test_clinical_models.py](#module-30e2a0a81d35) | 15 |
| [tests/test_cluster_bootstrap.py](#module-f4881086c612) | 23 |
| [tests/test_cohort_patient_splits.py](#module-675b36f2ff55) | 13 |
| [tests/test_cohort_splits.py](#module-532fbaae8b51) | 15 |
| [tests/test_decision_features.py](#module-56c4cbf31c2e) | 12 |
| [tests/test_llm_formal_summary.py](#module-1878750957f1) | 22 |
| [tests/test_llm_run_summary.py](#module-d1b73e75fd32) | 23 |
| [tests/test_outcomes.py](#module-0f1dce581793) | 13 |
| [tests/test_run_reproduction.py](#module-bd129354456e) | 8 |
| [tests/test_science.py](#module-1053c15840e5) | 13 |
| [tests/test_units.py](#module-996a7bd873d5) | 4 |

<a id="module-13a578d39606"></a>

## plot_results.py

[Open source](../plot_results.py)

Source module docstring:

> Render selected budget curves from bundled aggregate metrics; no fitting or API calls.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L8](../plot_results.py#L8) | function/method | <code>main()</code> |  |

<a id="module-43dd4fabe3da"></a>

## run_reproduction.py

[Open source](../run_reproduction.py)

Source module docstring:

> Offline replay of two selected APRIL baselines using unchanged numerical cores.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L24](../run_reproduction.py#L24) | function/method | <code>sha(path)</code> |  |
| [L32](../run_reproduction.py#L32) | function/method | <code>load(path)</code> |  |
| [L36](../run_reproduction.py#L36) | function/method | <code>save(path, value)</code> |  |
| [L44](../run_reproduction.py#L44) | function/method | <code>inside(root, relative)</code> |  |
| [L54](../run_reproduction.py#L54) | function/method | <code>verify(path, expected)</code> |  |
| [L59](../run_reproduction.py#L59) | function/method | <code>numbers(text, allowed)</code> |  |
| [L66](../run_reproduction.py#L66) | function/method | <code>check_close(actual, expected, label)</code> |  |
| [L72](../run_reproduction.py#L72) | function/method | <code>compare_tree(actual, expected, label='model')</code> |  |
| [L89](../run_reproduction.py#L89) | function/method | <code>artifact(root, reference)</code> |  |
| [L98](../run_reproduction.py#L98) | function/method | <code>verify_sources(root, index, case)</code> |  |
| [L147](../run_reproduction.py#L147) | function/method | <code>read_draws(directory, manifest, split, task, *, model=None, originals=None, dm_directory=None)</code> |  |
| [L179](../run_reproduction.py#L179) | function/method | <code>full_point(point, task, split, budget)</code> |  |
| [L185](../run_reproduction.py#L185) | function/method | <code>zero_records(originals)</code> |  |
| [L191](../run_reproduction.py#L191) | function/method | <code>prepare_case(root, index, case, budgets)</code> |  |
| [L225](../run_reproduction.py#L225) | function/method | <code>annotations_for(dataset, point_dir, point, case, budget, event_index)</code> |  |
| [L240](../run_reproduction.py#L240) | function/method | <code>commit_fit(directory, record, models, identity)</code> | Commit both files and their hashes atomically; never overwrite a draw. |
| [L253](../run_reproduction.py#L253) | function/method | <code>read_fit(directory, identity)</code> |  |
| [L262](../run_reproduction.py#L262) | function/method | <code>fresh_case(case_id, case, index, dirs, manifests, originals, cached, budgets, draw_ids, refit_dm, output, resume, plan_sha256)</code> |  |
| [L371](../run_reproduction.py#L371) | function/method | <code>execute(args)</code> |  |
| [L463](../run_reproduction.py#L463) | function/method | <code>main(argv=None)</code> |  |

<a id="module-f4eaec313b57"></a>

## scripts/check_repository_boundary.py

[Open source](../scripts/check_repository_boundary.py)

Source module docstring:

> Check a data-free public worktree before staging/pushing; stdlib only. This checks paths, known literal secrets, machine-specific locations, and patient-row keys in serialized reports. It deliberately does not classify numeric identifiers in Python/SQL synthetic fixtures as patient data. It does not inspect Git history or infer whether a reviewed PDF contains patient data.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L60](../scripts/check_repository_boundary.py#L60) | function/method | <code>patient_key_present(value)</code> |  |
| [L68](../scripts/check_repository_boundary.py#L68) | function/method | <code>inspect(root)</code> |  |
| [L78](../scripts/check_repository_boundary.py#L78) | function/method | <code>inspect.add(path, reason)</code> |  |
| [L172](../scripts/check_repository_boundary.py#L172) | function/method | <code>self_test()</code> |  |
| [L201](../scripts/check_repository_boundary.py#L201) | function/method | <code>main()</code> |  |

<a id="module-f2cefc04b3de"></a>

## scripts/generate_code_index.py

[Open source](../scripts/generate_code_index.py)

Source module docstring:

> Generate a source-linked Python symbol index without importing project modules.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L13](../scripts/generate_code_index.py#L13) | function/method | <code>escape(value: str) -&gt; str</code> |  |
| [L17](../scripts/generate_code_index.py#L17) | function/method | <code>source_files() -&gt; list[Path]</code> |  |
| [L26](../scripts/generate_code_index.py#L26) | function/method | <code>symbols(tree: ast.AST) -&gt; list[tuple[int, str, str, str]]</code> |  |
| [L29](../scripts/generate_code_index.py#L29) | function/method | <code>symbols.visit(node: ast.AST, parents: tuple[str, ...]=()) -&gt; None</code> |  |
| [L49](../scripts/generate_code_index.py#L49) | function/method | <code>generate() -&gt; str</code> |  |

<a id="module-35194e4c54ad"></a>

## scripts/run_clinical_baseline.py

[Open source](../scripts/run_clinical_baseline.py)

Source module docstring:

> Fit local clinical policy clones and OLS DM point baselines on complete artifacts.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L39](../scripts/run_clinical_baseline.py#L39) | function/method | <code>validate_protocol(protocol)</code> |  |
| [L58](../scripts/run_clinical_baseline.py#L58) | function/method | <code>sha(path)</code> |  |
| [L65](../scripts/run_clinical_baseline.py#L65) | function/method | <code>now()</code> |  |
| [L69](../scripts/run_clinical_baseline.py#L69) | function/method | <code>save(path, value)</code> |  |
| [L76](../scripts/run_clinical_baseline.py#L76) | function/method | <code>action_counts(values, task)</code> |  |
| [L80](../scripts/run_clinical_baseline.py#L80) | function/method | <code>classification_report(y, probabilities, train_actions, task)</code> |  |
| [L113](../scripts/run_clinical_baseline.py#L113) | function/method | <code>usable_policy(model)</code> |  |
| [L119](../scripts/run_clinical_baseline.py#L119) | function/method | <code>score_policy(model, dataset, train, validation)</code> |  |
| [L133](../scripts/run_clinical_baseline.py#L133) | function/method | <code>point_dm(policy, reward_model, dataset, evaluation, behavior_train, dest, batch_size=5000)</code> |  |
| [L184](../scripts/run_clinical_baseline.py#L184) | function/method | <code>run(source)</code> |  |
| [L244](../scripts/run_clinical_baseline.py#L244) | function/method | <code>main(argv=None)</code> |  |

<a id="module-914225b0c929"></a>

## scripts/run_clinical_bootstrap.py

[Open source](../scripts/run_clinical_bootstrap.py)

Source module docstring:

> Resumable, local-only 500-draw patient bootstrap for clinical DM. Each committed draw is immutable. Interrupted uncommitted draws can be replayed under their original key; failed draws are never replaced by new random draws.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L51](../scripts/run_clinical_bootstrap.py#L51) | function/method | <code>sha(path)</code> |  |
| [L59](../scripts/run_clinical_bootstrap.py#L59) | function/method | <code>now()</code> |  |
| [L63](../scripts/run_clinical_bootstrap.py#L63) | function/method | <code>save(path, value)</code> |  |
| [L73](../scripts/run_clinical_bootstrap.py#L73) | function/method | <code>exclusive_run(dest)</code> |  |
| [L86](../scripts/run_clinical_bootstrap.py#L86) | function/method | <code>validate_protocol(protocol)</code> |  |
| [L110](../scripts/run_clinical_bootstrap.py#L110) | function/method | <code>validate_model_protocol(protocol)</code> |  |
| [L126](../scripts/run_clinical_bootstrap.py#L126) | function/method | <code>commit_draw(dest, record, payload, draws)</code> | Publish the complete private draw directory with one atomic rename. |
| [L146](../scripts/run_clinical_bootstrap.py#L146) | function/method | <code>read_committed(dest, task, split)</code> |  |
| [L167](../scripts/run_clinical_bootstrap.py#L167) | function/method | <code>summarize_results(populations, records)</code> |  |
| [L182](../scripts/run_clinical_bootstrap.py#L182) | function/method | <code>run(input_directory=None, resume_directory=None, max_new_draws=None)</code> |  |

<a id="module-2324533abe49"></a>

## scripts/run_clinical_dmplus.py

[Open source](../scripts/run_clinical_dmplus.py)

Source module docstring:

> Fit local pilot DM+ points using saved G3 models and verified LLM receipts.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L34](../scripts/run_clinical_dmplus.py#L34) | function/method | <code>save(path, value)</code> |  |
| [L43](../scripts/run_clinical_dmplus.py#L43) | function/method | <code>local_path(value, parent)</code> |  |
| [L50](../scripts/run_clinical_dmplus.py#L50) | function/method | <code>load_baseline(folder)</code> |  |
| [L69](../scripts/run_clinical_dmplus.py#L69) | function/method | <code>run(baseline_directory, summary_directory, output_directory=None)</code> |  |
| [L176](../scripts/run_clinical_dmplus.py#L176) | function/method | <code>main(argv=None)</code> |  |

<a id="module-ad0ecf3c30c5"></a>

## scripts/run_clinical_dmplus_bootstrap.py

[Open source](../scripts/run_clinical_dmplus_bootstrap.py)

Source module docstring:

> Resume paired DM+ fits against immutable completed patient-bootstrap DM draws.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L40](../scripts/run_clinical_dmplus_bootstrap.py#L40) | function/method | <code>validate_protocol(value)</code> |  |
| [L53](../scripts/run_clinical_dmplus_bootstrap.py#L53) | function/method | <code>load_dm_source(folder)</code> |  |
| [L85](../scripts/run_clinical_dmplus_bootstrap.py#L85) | function/method | <code>load_point_source(folder, task)</code> |  |
| [L100](../scripts/run_clinical_dmplus_bootstrap.py#L100) | function/method | <code>read_committed(dest, task, originals, dm_source=None)</code> |  |
| [L129](../scripts/run_clinical_dmplus_bootstrap.py#L129) | function/method | <code>commit_draw(folder, record, payload)</code> |  |
| [L141](../scripts/run_clinical_dmplus_bootstrap.py#L141) | function/method | <code>summarize(originals, records, point)</code> |  |
| [L159](../scripts/run_clinical_dmplus_bootstrap.py#L159) | function/method | <code>_run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None)</code> |  |
| [L251](../scripts/run_clinical_dmplus_bootstrap.py#L251) | function/method | <code>_run.checkpoint(status)</code> |  |
| [L312](../scripts/run_clinical_dmplus_bootstrap.py#L312) | function/method | <code>run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None)</code> |  |
| [L322](../scripts/run_clinical_dmplus_bootstrap.py#L322) | function/method | <code>main(argv=None)</code> |  |

<a id="module-64fb5915b538"></a>

## scripts/run_clinical_dmplus_bootstrap_budgets.py

[Open source](../scripts/run_clinical_dmplus_bootstrap_budgets.py)

Source module docstring:

> Fixed-budget prefixes with unchanged paired DM+ patient-bootstrap fits. New artifacts only. The saved DM draws, OLS, factual preprocessing, patient multiplicities and conditional squared-error t-test are unchanged. Budget 0 reuses original DM; existing budget 500 artifacts remain the authoritative endpoints. Budget 500 here is supported for bounded equivalence checks.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L51](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L51) | function/method | <code>source_path(name)</code> |  |
| [L55](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L55) | function/method | <code>validate_annotation_budget(value)</code> |  |
| [L61](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L61) | function/method | <code>validate_protocol(value)</code> |  |
| [L74](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L74) | function/method | <code>load_dm_source(folder)</code> |  |
| [L106](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L106) | function/method | <code>validate_model_key(model_key)</code> |  |
| [L112](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L112) | function/method | <code>load_point_source(folder, task, model_key)</code> |  |
| [L130](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L130) | function/method | <code>read_committed(dest, task, originals, dm_source=None, *, model_key, annotation_budget)</code> |  |
| [L162](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L162) | function/method | <code>commit_draw(folder, record, payload)</code> |  |
| [L174](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L174) | function/method | <code>summarize(originals, records, point, annotation_budget)</code> |  |
| [L192](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L192) | function/method | <code>_run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None, model_key=None, annotation_budget=None, verification_root=None)</code> |  |
| [L303](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L303) | function/method | <code>_run.checkpoint(status)</code> |  |
| [L365](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L365) | function/method | <code>run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None, model_key=None, annotation_budget=None, verification_root=None)</code> |  |
| [L375](../scripts/run_clinical_dmplus_bootstrap_budgets.py#L375) | function/method | <code>main(argv=None)</code> |  |

<a id="module-8b391cd054d8"></a>

## scripts/run_clinical_dmplus_bootstrap_models.py

[Open source](../scripts/run_clinical_dmplus_bootstrap_models.py)

Source module docstring:

> Explicit model selection for unchanged paired DM+ patient-bootstrap fits.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L41](../scripts/run_clinical_dmplus_bootstrap_models.py#L41) | function/method | <code>validate_protocol(value)</code> |  |
| [L54](../scripts/run_clinical_dmplus_bootstrap_models.py#L54) | function/method | <code>load_dm_source(folder)</code> |  |
| [L86](../scripts/run_clinical_dmplus_bootstrap_models.py#L86) | function/method | <code>validate_model_key(model_key)</code> |  |
| [L92](../scripts/run_clinical_dmplus_bootstrap_models.py#L92) | function/method | <code>load_point_source(folder, task, model_key)</code> |  |
| [L110](../scripts/run_clinical_dmplus_bootstrap_models.py#L110) | function/method | <code>read_committed(dest, task, originals, dm_source=None, *, model_key)</code> |  |
| [L141](../scripts/run_clinical_dmplus_bootstrap_models.py#L141) | function/method | <code>commit_draw(folder, record, payload)</code> |  |
| [L153](../scripts/run_clinical_dmplus_bootstrap_models.py#L153) | function/method | <code>summarize(originals, records, point)</code> |  |
| [L171](../scripts/run_clinical_dmplus_bootstrap_models.py#L171) | function/method | <code>_run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None, model_key=None)</code> |  |
| [L268](../scripts/run_clinical_dmplus_bootstrap_models.py#L268) | function/method | <code>_run.checkpoint(status)</code> |  |
| [L329](../scripts/run_clinical_dmplus_bootstrap_models.py#L329) | function/method | <code>run(dm_bootstrap_directory=None, point_directory=None, output_directory=None, resume_directory=None, max_new_draws=None, model_key=None)</code> |  |
| [L339](../scripts/run_clinical_dmplus_bootstrap_models.py#L339) | function/method | <code>main(argv=None)</code> |  |

<a id="module-7858272039e0"></a>

## scripts/run_clinical_dmplus_formal.py

[Open source](../scripts/run_clinical_dmplus_formal.py)

Source module docstring:

> Fit one completed formal LLM's fixed 0--500-prefix DM+ points, entirely locally.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L29](../scripts/run_clinical_dmplus_formal.py#L29) | function/method | <code>run(plan_directory, run_directory, baseline_directories, output_directory, model_key='deepseek')</code> |  |
| [L136](../scripts/run_clinical_dmplus_formal.py#L136) | function/method | <code>main(argv=None)</code> |  |

<a id="module-50d7c6de8573"></a>

## scripts/summarize_five_llm_runs.py

[Open source](../scripts/summarize_five_llm_runs.py)

Source module docstring:

> Collect private five-model pilot replies and factual metrics without API calls.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L15](../scripts/summarize_five_llm_runs.py#L15) | function/method | <code>main(argv=None)</code> |  |

<a id="module-01beac891d00"></a>

## scripts/summarize_formal_llm_run.py

[Open source](../scripts/summarize_formal_llm_run.py)

Source module docstring:

> Revalidate formal LLM annotations and factual metrics locally, without API calls.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L15](../scripts/summarize_formal_llm_run.py#L15) | function/method | <code>main(argv=None)</code> |  |

<a id="module-053a77878e7e"></a>

## src/april_repro/__init__.py

[Open source](../src/april_repro/__init__.py)

Source module docstring:

> Independent APRIL reproduction; clinical protocol remains draft.

No named function or class definitions in this file.

<a id="module-3877859ece09"></a>

## src/april_repro/__main__.py

[Open source](../src/april_repro/__main__.py)

No named function or class definitions in this file.

<a id="module-5b21272378ec"></a>

## src/april_repro/cli.py

[Open source](../src/april_repro/cli.py)

Source module docstring:

> Checkout-oriented command line for audit and database discovery.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L35](../src/april_repro/cli.py#L35) | function/method | <code>project_root(explicit: str &#124; None=None) -&gt; Path</code> |  |
| [L47](../src/april_repro/cli.py#L47) | function/method | <code>emit(value: object) -&gt; None</code> |  |
| [L51](../src/april_repro/cli.py#L51) | function/method | <code>read_protocol(root: Path) -&gt; dict</code> |  |
| [L56](../src/april_repro/cli.py#L56) | function/method | <code>validate_protocol(config: dict) -&gt; list[str]</code> |  |
| [L96](../src/april_repro/cli.py#L96) | function/method | <code>doctor(root: Path) -&gt; int</code> |  |
| [L159](../src/april_repro/cli.py#L159) | function/method | <code>protocol_check(root: Path, require_frozen: bool) -&gt; int</code> |  |
| [L212](../src/april_repro/cli.py#L212) | function/method | <code>db_run(root: Path, inspect: bool, timeout_ms: int) -&gt; int</code> |  |
| [L242](../src/april_repro/cli.py#L242) | function/method | <code>main(argv: list[str] &#124; None=None) -&gt; int</code> |  |

<a id="module-986af6fec78e"></a>

## src/april_repro/clinical_bootstrap.py

[Open source](../src/april_repro/clinical_bootstrap.py)

Source module docstring:

> Refit and evaluate one paired, patient-bootstrap clinical DM draw. The target policy and behavior reward model each fit their own preprocessing on their resampled training events. DM and its observed-reward proxy use exactly the same resampled target-validation event distribution. No patient means, prediction clipping, behavior policy refitting, or rare-action redrawing occur.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L26](../src/april_repro/clinical_bootstrap.py#L26) | function/method | <code>_usable_policy(model, state)</code> |  |
| [L32](../src/april_repro/clinical_bootstrap.py#L32) | function/method | <code>_action_counts(values, task)</code> |  |
| [L36](../src/april_repro/clinical_bootstrap.py#L36) | function/method | <code>_diagnostics(payload)</code> |  |
| [L60](../src/april_repro/clinical_bootstrap.py#L60) | function/method | <code>run_dm_draw(dataset, populations, draw_id, seed=DEFAULT_SEED, batch_size=5000)</code> | Return (aggregate record, model-state payload, private ClusterDraw objects). |
| [L95](../src/april_repro/clinical_bootstrap.py#L95) | function/method | <code>run_dm_draw.fail(reason)</code> |  |

<a id="module-310e99800810"></a>

## src/april_repro/clinical_bootstrap_statistics.py

[Open source](../src/april_repro/clinical_bootstrap_statistics.py)

Source module docstring:

> Summarize one layer of bootstrap errors without inventing sampling SEs. &#96;&#96;summarize_bootstrap_draws(records, planned_draws=500)&#96;&#96; accepts an iterable of mappings. &#96;&#96;draw_id&#96;&#96; is a zero-based integer in &#96;&#96;[0, planned_draws)&#96;&#96;; &#96;&#96;status&#96;&#96; is &#96;&#96;complete&#96;&#96;, &#96;&#96;failed&#96;&#96; or &#96;&#96;pending&#96;&#96;. Complete records require finite real numbers in &#96;&#96;dm_value&#96;&#96;, &#96;&#96;observed_reference_value&#96;&#96;, and &#96;&#96;signed_error&#96;&#96;. The latter must equal DM minus reference within relative tolerance 1e-10 and absolute tolerance 1e-12. Incomplete records must omit those three numeric fields or set them to None. Additional fields (e.g. a failure reason) are allowed and do not affect arithmetic. Inputs are never modified. Return schema (all values are JSON-safe): * schema_version: &#96;&#96;clinical-bootstrap-statistics-v1&#96;&#96;; * status: &#96;&#96;complete&#96;&#96; only if all planned draws completed, else &#96;&#96;incomplete&#96;&#96;; * planned_draws / completed_draws / failed_draws / pending_draws: integer counts; * completed_draw_ids / failed_draw_ids / pending_draw_ids: sorted integer lists. Missing records count as pending, as do explicit pending records; * primary_metrics: metrics object only when every planned draw completed, otherwise None. A failed draw is never silently removed from its denominator; * diagnostic_valid_draw_metrics: metrics over completed draws only when the run is incomplete and at least one draw completed, otherwise None; * diagnostic_valid_draw_metrics_label: &#96;&#96;partial_valid_draws_only_not_primary&#96;&#96; when diagnostic metrics exist, otherwise None. Each metrics object contains &#96;&#96;draw_count&#96;&#96;, &#96;&#96;rmse = sqrt(mean(e**2))&#96;&#96;, &#96;&#96;bootstrap_se_value = sample_sd(dm_value)&#96;&#96;, &#96;&#96;bootstrap_sd_error = sample_sd(e)&#96;&#96;, &#96;&#96;rmse_mc_se_delta = sample_sd(e**2)/(2*sqrt(B)*rmse)&#96;&#96;, &#96;&#96;rmse_mc_se_lower_bound = max(0, rmse-rmse_mc_se_delta)&#96;&#96;, and &#96;&#96;rmse_mc_se_upper_bound = rmse+rmse_mc_se_delta&#96;&#96;. The SDs use ddof=1; &#96;&#96;standard_deviation_ddof&#96;&#96; is 1. For B&lt;2 the SDs, MC-SE and bounds are None. For B&gt;=2 with every error zero, RMSE and its empirical MC-SE/bounds are zero. &#96;&#96;rmse_error_bar_kind&#96;&#96; is &#96;&#96;finite_B_monte_carlo_standard_error_delta&#96;&#96;. The delta MC-SE measures finite-B numerical uncertainty conditional on the observed dataset and chosen bootstrap scheme. It is NOT a sampling standard error of RMSE and does not claim to recover APRIL's undisclosed error-bar implementation. The observed reference remains a proxy, not causal truth. This module knows no populations: an empty population is the caller's &#96;&#96;not_estimable&#96;&#96; condition; an empty records iterable here means all pending. No p-values, Table 2 tests, resampling, fitting, or data access occur here.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L56](../src/april_repro/clinical_bootstrap_statistics.py#L56) | function/method | <code>_finite_number(value: Any, label: str) -&gt; float</code> |  |
| [L68](../src/april_repro/clinical_bootstrap_statistics.py#L68) | function/method | <code>_finite_result(value: float, label: str) -&gt; float</code> |  |
| [L74](../src/april_repro/clinical_bootstrap_statistics.py#L74) | function/method | <code>_sample_sd(values: list[float]) -&gt; float &#124; None</code> | Scaled ddof=1 SD; avoid squaring otherwise representable large values. |
| [L87](../src/april_repro/clinical_bootstrap_statistics.py#L87) | function/method | <code>_metrics(complete: list[tuple[int, float, float]]) -&gt; dict[str, Any]</code> |  |
| [L122](../src/april_repro/clinical_bootstrap_statistics.py#L122) | function/method | <code>summarize_bootstrap_draws(records: Iterable[Mapping[str, Any]], planned_draws: int=500) -&gt; dict[str, Any]</code> | Validate draw identities/results and report primary or partial metrics. |

<a id="module-12cd3f11d1c3"></a>

## src/april_repro/clinical_dataset.py

[Open source](../src/april_repro/clinical_dataset.py)

Source module docstring:

> Load private treatment features into compact arrays without positional joins. Only the fifteen declared pretreatment features enter the model matrix. Patient groups are already represented by splits.csv and are never predictor inputs. CSV parsing is streaming: the largest Python mapping contains event IDs and integer array offsets, not patient row dictionaries. Empty features become NaN; all fitting and imputation remain the responsibility of training-only code.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L39](../src/april_repro/clinical_dataset.py#L39) | class | <code>ClinicalDataset()</code> |  |
| [L56](../src/april_repro/clinical_dataset.py#L56) | function/method | <code>ClinicalDataset.X(self)</code> |  |
| [L59](../src/april_repro/clinical_dataset.py#L59) | function/method | <code>ClinicalDataset.mask(self, split, role, fold=None)</code> | Return one boolean event mask without copying rows or feature data. |
| [L69](../src/april_repro/clinical_dataset.py#L69) | function/method | <code>_sha(path)</code> |  |
| [L77](../src/april_repro/clinical_dataset.py#L77) | function/method | <code>_rows(path, columns, expected_hash)</code> | Parse and hash the same byte stream, including CSV quoted multiline fields. |
| [L81](../src/april_repro/clinical_dataset.py#L81) | function/method | <code>_rows.lines()</code> |  |
| [L97](../src/april_repro/clinical_dataset.py#L97) | function/method | <code>_identifier(value)</code> |  |
| [L103](../src/april_repro/clinical_dataset.py#L103) | function/method | <code>_event(value)</code> |  |
| [L109](../src/april_repro/clinical_dataset.py#L109) | function/method | <code>_clock(value)</code> |  |
| [L119](../src/april_repro/clinical_dataset.py#L119) | function/method | <code>_finite(value, label)</code> |  |
| [L129](../src/april_repro/clinical_dataset.py#L129) | function/method | <code>_feature(value, name)</code> |  |
| [L143](../src/april_repro/clinical_dataset.py#L143) | function/method | <code>_action(value, task)</code> |  |
| [L149](../src/april_repro/clinical_dataset.py#L149) | function/method | <code>_count(actual, expected, label)</code> |  |
| [L154](../src/april_repro/clinical_dataset.py#L154) | function/method | <code>_check_counts(expected, events, subjects, admissions, actions, task)</code> |  |
| [L164](../src/april_repro/clinical_dataset.py#L164) | function/method | <code>load_clinical_dataset(artifact_directory)</code> | Load a complete treatment feature artifact; never access DBs or services. |
| [L252](../src/april_repro/clinical_dataset.py#L252) | function/method | <code>load_clinical_dataset.joined(row, kind)</code> |  |

<a id="module-e441a7c7e804"></a>

## src/april_repro/clinical_dmplus.py

[Open source](../src/april_repro/clinical_dmplus.py)

Source module docstring:

> Local DM+ point bridge for validated LLM review-pilot annotations. This uses the adopted G3 numeric dose design and original behavior-training preprocessing. It reuses the saved target policy and evaluation distribution. It does not run bootstrap or claim the paper's 500-annotation comparison.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L28](../src/april_repro/clinical_dmplus.py#L28) | function/method | <code>file_sha256(path)</code> |  |
| [L37](../src/april_repro/clinical_dmplus.py#L37) | class | <code>AnnotationEvidence()</code> |  |
| [L45](../src/april_repro/clinical_dmplus.py#L45) | class | <code>Counterfactual()</code> |  |
| [L55](../src/april_repro/clinical_dmplus.py#L55) | function/method | <code>load_verified_annotations(summary_directory)</code> | Recreate the saved summary from packet/attempt raw evidence, offline. |
| [L93](../src/april_repro/clinical_dmplus.py#L93) | function/method | <code>select_counterfactuals(dataset, evidence, split, model_key, event_index=None)</code> | Join one source/split's explicit CF consumers to original training rows. |
| [L151](../src/april_repro/clinical_dmplus.py#L151) | function/method | <code>fit_augmented_reward(dataset, behavior_train, baseline, annotations)</code> | Equal-weight factual + CF OLS with the saved factual preprocessor fixed. |
| [L198](../src/april_repro/clinical_dmplus.py#L198) | function/method | <code>evaluate_pair(dataset, split, target_policy, baseline, augmented, batch_size=5000)</code> | Use exactly one saved target policy/d0 for both OPE point estimates. |
| [L250](../src/april_repro/clinical_dmplus.py#L250) | function/method | <code>verify_saved_dm(result, saved)</code> | Reject a changed target policy, evaluation population, or baseline value. |

<a id="module-fb6d3745e499"></a>

## src/april_repro/clinical_dmplus_bootstrap.py

[Open source](../src/april_repro/clinical_dmplus_bootstrap.py)

Source module docstring:

> Pair DM+ with an already committed patient-bootstrap DM draw. The fixed annotation cache follows each source behavior patient's *same* multiplicity as the factual rows. This module performs no I/O or new sampling experiment: deterministic draw replay verifies the supplied original counts. The saved factual preprocessor and target policy are never refitted.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L26](../src/april_repro/clinical_dmplus_bootstrap.py#L26) | function/method | <code>replay_original_draw(dataset, populations, original_record, original_payload, saved_counts)</code> | Verify and return the original three ClusterDraw objects. |
| [L77](../src/april_repro/clinical_dmplus_bootstrap.py#L77) | function/method | <code>annotation_multiplicities(dataset, population, draw, annotations)</code> | One integer weight per unique cached CF, inherited from its patient. |
| [L108](../src/april_repro/clinical_dmplus_bootstrap.py#L108) | function/method | <code>fit_paired_augmented_reward(dataset, behavior_indices, baseline, annotations, multiplicities)</code> | Actual repeated-row OLS; no Gram approximation or independent CF draw. |
| [L151](../src/april_repro/clinical_dmplus_bootstrap.py#L151) | function/method | <code>_evaluate(dataset, evaluation, policy, baseline, augmented, batch_size)</code> |  |
| [L179](../src/april_repro/clinical_dmplus_bootstrap.py#L179) | function/method | <code>run_paired_draw(dataset, populations, original_record, original_payload, saved_counts, annotations, *, requested_budget=500, batch_size=5000)</code> | Return a DM+-schema aggregate record and its fitted reward state. |

<a id="module-9274e63d0bca"></a>

## src/april_repro/clinical_dmplus_bootstrap_statistics.py

[Open source](../src/april_repro/clinical_dmplus_bootstrap_statistics.py)

Source module docstring:

> Paired DM/DM+ bootstrap arithmetic for the adopted D007 local protocol. Inputs use the original clinical bootstrap record schema: &#96;&#96;draw_id&#96;&#96;, &#96;&#96;status&#96;&#96;, &#96;&#96;dm_value&#96;&#96;, &#96;&#96;observed_reference_value&#96;&#96;, and &#96;&#96;signed_error&#96;&#96;. The DM+ list also names its estimate &#96;&#96;dm_value&#96;&#96; for compatibility with the existing single-method statistics helper. Pairing is by integer draw ID, never list order. Complete pairs must have exactly matching references and matching &#96;&#96;pair_metadata&#96;&#96;, &#96;&#96;population_draw_metadata&#96;&#96;, &#96;&#96;task&#96;&#96;, &#96;&#96;split&#96;&#96; and &#96;&#96;seed&#96;&#96; whenever either member supplies those fields. The caller binds the metadata to the resampled populations, policy, preprocessing and input artifacts. This module cannot independently verify those source artifacts. Every planned ID remains in the denominator. Only all planned complete pairs produce primary metrics; a failed member makes a pair failed, and any other missing member makes it pending. Partial valid-pair arithmetic is explicitly diagnostic and does not replace the complete experiment. RMSE and its finite-B Monte Carlo SE reuse clinical_bootstrap_statistics. The two-sided paired t-test compares per-draw squared errors, DM minus DM+. It describes the conditional bootstrap distribution, not 500 independent new patient cohorts or the undisclosed original APRIL Table 2 implementation. The 95% percentile interval instead describes paired absolute-error gain; it is not a confidence interval of the RMSE difference. Positive gain favors DM+. The proportion of positive gains is descriptive, not a p-value. All-zero squared-error differences have t=0,p=1. Constant nonzero differences are explicitly degenerate with t/p=None. No patient-level data access, resampling, fitting, LLM requests or multiple-testing adjustment occurs here.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L44](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L44) | function/method | <code>_finite(value: Any, label: str) -&gt; float</code> |  |
| [L56](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L56) | function/method | <code>_mean(values: list[float]) -&gt; float</code> |  |
| [L61](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L61) | function/method | <code>_sample_sd(values: list[float]) -&gt; float &#124; None</code> |  |
| [L73](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L73) | function/method | <code>_test(dm_squares: list[float], plus_squares: list[float], gains: list[float], alpha: float) -&gt; dict[str, Any]</code> |  |
| [L113](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L113) | function/method | <code>_metrics(dm: list[dict[str, Any]], plus: list[dict[str, Any]], planned_draws: int, alpha: float) -&gt; dict[str, Any]</code> |  |
| [L152](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L152) | function/method | <code>_full_point(full_point: Mapping[str, Any] &#124; None) -&gt; dict[str, Any] &#124; None</code> |  |
| [L171](../src/april_repro/clinical_dmplus_bootstrap_statistics.py#L171) | function/method | <code>summarize_paired_bootstrap_draws(dm_records: Iterable[Mapping[str, Any]], dmplus_records: Iterable[Mapping[str, Any]], planned_draws: int=500, *, full_point: Mapping[str, Any] &#124; None=None, alpha: float=0.05) -&gt; dict[str, Any]</code> | Validate and summarize all planned pairs without dropping failures. |

<a id="module-e11f3ddc0558"></a>

## src/april_repro/clinical_dmplus_formal.py

[Open source](../src/april_repro/clinical_dmplus_formal.py)

Source module docstring:

> Offline fixed-prefix DM+ bridge for one completed formal annotation source. Invalid completed replies remain inside their preselected budget. The available valid subset may yield a diagnostic point, but never becomes an exact B-valid- annotation result. No provider calls or outcome-dependent replacement occur.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L25](../src/april_repro/clinical_dmplus_formal.py#L25) | function/method | <code>_id_set(value)</code> |  |
| [L31](../src/april_repro/clinical_dmplus_formal.py#L31) | function/method | <code>load_model_evidence(plan_directory, run_directory, model_key)</code> | Revalidate one model's complete immutable replies, irrespective of peers. |
| [L102](../src/april_repro/clinical_dmplus_formal.py#L102) | function/method | <code>select_prefix(dataset, evidence, split, model_key, budget, event_index=None)</code> | Use planned consumer rank, preserving failures inside every prefix. |
| [L136](../src/april_repro/clinical_dmplus_formal.py#L136) | function/method | <code>verify_evidence_unchanged(evidence)</code> |  |

<a id="module-417bc28543c4"></a>

## src/april_repro/clinical_models.py

[Open source](../src/april_repro/clinical_models.py)

Source module docstring:

> G3 clinical models with training-only transforms and JSON coefficient export. These are recorded project choices for undisclosed APRIL implementation details. Inputs are numeric arrays in the fifteen-feature order; NaN means missing. Gender is F=0/M=1. Fixed binary dictionaries do not depend on training support. No patient identities, outcomes, or actions enter the context transformer.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L24](../src/april_repro/clinical_models.py#L24) | function/method | <code>_numpy()</code> |  |
| [L32](../src/april_repro/clinical_models.py#L32) | function/method | <code>_versions()</code> |  |
| [L39](../src/april_repro/clinical_models.py#L39) | function/method | <code>_matrix(values)</code> |  |
| [L58](../src/april_repro/clinical_models.py#L58) | function/method | <code>_vector(values, length, label)</code> |  |
| [L69](../src/april_repro/clinical_models.py#L69) | function/method | <code>_actions(values, length, task)</code> |  |
| [L79](../src/april_repro/clinical_models.py#L79) | function/method | <code>_json_copy(value)</code> |  |
| [L86](../src/april_repro/clinical_models.py#L86) | class | <code>Preprocessor()</code> |  |
| [L87](../src/april_repro/clinical_models.py#L87) | function/method | <code>Preprocessor.__init__(self, state)</code> |  |
| [L110](../src/april_repro/clinical_models.py#L110) | function/method | <code>Preprocessor.status(self)</code> |  |
| [L114](../src/april_repro/clinical_models.py#L114) | function/method | <code>Preprocessor.columns(self)</code> |  |
| [L117](../src/april_repro/clinical_models.py#L117) | function/method | <code>Preprocessor.to_dict(self)</code> |  |
| [L121](../src/april_repro/clinical_models.py#L121) | function/method | <code>Preprocessor.from_dict(cls, state)</code> |  |
| [L124](../src/april_repro/clinical_models.py#L124) | function/method | <code>Preprocessor.transform(self, values)</code> |  |
| [L144](../src/april_repro/clinical_models.py#L144) | function/method | <code>fit_preprocessor(values)</code> |  |
| [L183](../src/april_repro/clinical_models.py#L183) | class | <code>_Model()</code> |  |
| [L186](../src/april_repro/clinical_models.py#L186) | function/method | <code>_Model.__init__(self, state)</code> |  |
| [L196](../src/april_repro/clinical_models.py#L196) | function/method | <code>_Model.status(self)</code> |  |
| [L200](../src/april_repro/clinical_models.py#L200) | function/method | <code>_Model.task(self)</code> |  |
| [L204](../src/april_repro/clinical_models.py#L204) | function/method | <code>_Model.actions(self)</code> |  |
| [L208](../src/april_repro/clinical_models.py#L208) | function/method | <code>_Model.metadata(self)</code> |  |
| [L211](../src/april_repro/clinical_models.py#L211) | function/method | <code>_Model.to_dict(self)</code> |  |
| [L215](../src/april_repro/clinical_models.py#L215) | function/method | <code>_Model.from_dict(cls, state)</code> |  |
| [L218](../src/april_repro/clinical_models.py#L218) | function/method | <code>_Model._context(self, values)</code> |  |
| [L224](../src/april_repro/clinical_models.py#L224) | class | <code>PolicyFit(_Model)</code> |  |
| [L228](../src/april_repro/clinical_models.py#L228) | function/method | <code>PolicyFit.converged(self)</code> |  |
| [L232](../src/april_repro/clinical_models.py#L232) | function/method | <code>PolicyFit.n_iter(self)</code> |  |
| [L235](../src/april_repro/clinical_models.py#L235) | function/method | <code>PolicyFit.predict_proba(self, values)</code> |  |
| [L276](../src/april_repro/clinical_models.py#L276) | function/method | <code>PolicyFit.predict(self, values)</code> |  |
| [L281](../src/april_repro/clinical_models.py#L281) | class | <code>RewardFit(_Model)</code> |  |
| [L284](../src/april_repro/clinical_models.py#L284) | function/method | <code>RewardFit._base(self, values)</code> |  |
| [L293](../src/april_repro/clinical_models.py#L293) | function/method | <code>RewardFit.predict(self, values, actions)</code> |  |
| [L302](../src/april_repro/clinical_models.py#L302) | function/method | <code>RewardFit.predict_action_values(self, values)</code> |  |
| [L311](../src/april_repro/clinical_models.py#L311) | function/method | <code>_initial_state(kind, array, actions, task)</code> |  |
| [L324](../src/april_repro/clinical_models.py#L324) | function/method | <code>fit_policy(values, actions, task)</code> |  |
| [L358](../src/april_repro/clinical_models.py#L358) | function/method | <code>fit_reward(values, actions, rewards, task)</code> |  |

<a id="module-382d1440f0b3"></a>

## src/april_repro/cluster_bootstrap.py

[Open source](../src/april_repro/cluster_bootstrap.py)

Source module docstring:

> Patient bootstrap within fixed train/validation and behavior/target groups. Patient-cluster resampling is an explicit project choice, not a recovered APRIL implementation detail. Every selected patient's events carry that patient's multiplicity. Downstream estimators average repeated events, not patient means. There is exactly one draw per population/key, even when a rare action is absent.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L35](../src/april_repro/cluster_bootstrap.py#L35) | function/method | <code>_json(value)</code> |  |
| [L39](../src/april_repro/cluster_bootstrap.py#L39) | function/method | <code>_array_bytes(values)</code> |  |
| [L44](../src/april_repro/cluster_bootstrap.py#L44) | class | <code>ClusterDraw()</code> |  |
| [L51](../src/april_repro/cluster_bootstrap.py#L51) | function/method | <code>ClusterDraw.status(self)</code> |  |
| [L55](../src/april_repro/cluster_bootstrap.py#L55) | function/method | <code>ClusterDraw.draw_sha256(self)</code> |  |
| [L60](../src/april_repro/cluster_bootstrap.py#L60) | class | <code>ClusterPopulation()</code> |  |
| [L71](../src/april_repro/cluster_bootstrap.py#L71) | function/method | <code>ClusterPopulation.n_subjects(self)</code> |  |
| [L75](../src/april_repro/cluster_bootstrap.py#L75) | function/method | <code>ClusterPopulation.n_events(self)</code> |  |
| [L79](../src/april_repro/cluster_bootstrap.py#L79) | function/method | <code>ClusterPopulation.metadata(self)</code> |  |
| [L87](../src/april_repro/cluster_bootstrap.py#L87) | function/method | <code>ClusterPopulation.indices_from_counts(self, patient_counts)</code> | Replay compact counts; each original event repeats its cluster count. |
| [L105](../src/april_repro/cluster_bootstrap.py#L105) | function/method | <code>ClusterPopulation.draw(self, draw_id, *, seed=DEFAULT_SEED)</code> | Return one independent keyed draw, reproducible in any execution order. |
| [L147](../src/april_repro/cluster_bootstrap.py#L147) | function/method | <code>build_cluster_population(dataset, split, population)</code> | Build once per fixed population, without changing patient roles or folds. |

<a id="module-ecbf39339f2e"></a>

## src/april_repro/cohort_patient_splits.py

[Open source](../src/april_repro/cohort_patient_splits.py)

Source module docstring:

> Patient-disjoint APRIL subgroup candidates, preserving all eligible events. Section 3.4, p5 describes disjoint behavior/target sub-cohorts and separates patients by dosage. The paper does not specify how repeated decisions determine a patient's group. Here any high dose or any positive disease flag determines the corresponding patient-level target group. This is a retrospective project choice, not an inferred decision-time predictor or a recovered author rule. The event-level v1 module and its artifacts remain unchanged. Its input validation and global subject_fold are reused before patient roles replace the event roles. Outcome values never enter the calculation.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L25](../src/april_repro/cohort_patient_splits.py#L25) | function/method | <code>_gender(value)</code> |  |
| [L36](../src/april_repro/cohort_patient_splits.py#L36) | function/method | <code>_flag(value)</code> |  |
| [L50](../src/april_repro/cohort_patient_splits.py#L50) | function/method | <code>_counts(rows, task)</code> |  |
| [L61](../src/april_repro/cohort_patient_splits.py#L61) | function/method | <code>build_patient_cohort_splits(rows, task, *, seed=DEFAULT_SEED)</code> | Return private event assignments and aggregate patient-group summaries. |

<a id="module-f69dd38e736c"></a>

## src/april_repro/cohort_splits.py

[Open source](../src/april_repro/cohort_splits.py)

Source module docstring:

> APRIL cohort labels and globally stable subject-held-out folds. Paper facts: female -&gt; male, no renal disease -&gt; renal disease (K), no cirrhosis -&gt; cirrhosis (Na), and low -&gt; high dosage (section 3.4, p5). Project choices: K &lt;=20 versus 40; Na &lt;=200 versus &gt;=300, including zero in low dosage; SHA256 modulo five reserves approximately 20% of subjects. The input must contain already eligible decisions. Retrospective diagnosis flags are grouping labels only; this module creates no predictor features. Roles are assigned per decision. Subjects can occur in both dosage roles or have different diagnosis labels across admissions; their global fold never changes, and role overlap is explicitly reported rather than hidden.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L34](../src/april_repro/cohort_splits.py#L34) | function/method | <code>_identifier(value: Any, label: str) -&gt; str</code> |  |
| [L42](../src/april_repro/cohort_splits.py#L42) | function/method | <code>_flag(value: Any) -&gt; bool &#124; None</code> |  |
| [L56](../src/april_repro/cohort_splits.py#L56) | function/method | <code>subject_fold(subject_id: str &#124; int, *, seed: str=DEFAULT_SEED) -&gt; str</code> | Return a subject's global fold; task, action and cohort never enter it. |
| [L66](../src/april_repro/cohort_splits.py#L66) | function/method | <code>_action(value: Any, task: str) -&gt; int</code> |  |
| [L74](../src/april_repro/cohort_splits.py#L74) | function/method | <code>_role(row: dict, task: str, split: str, action: int) -&gt; tuple[str, str]</code> |  |
| [L93](../src/april_repro/cohort_splits.py#L93) | function/method | <code>_counts(rows: list[dict], task: str) -&gt; dict</code> |  |
| [L105](../src/april_repro/cohort_splits.py#L105) | function/method | <code>build_cohort_splits(rows: list[dict], task: str, *, seed: str=DEFAULT_SEED) -&gt; tuple[list[dict], dict]</code> | Return private event assignments and a patient-identifier-free summary. |

<a id="module-a47c0ca907b8"></a>

## src/april_repro/database.py

[Open source](../src/april_repro/database.py)

Source module docstring:

> Read-only PostgreSQL transport for metadata and registered profiling. No driver or password is bundled. CLI paths execute reviewed static SQL templates. This module never creates schemas, tables, extensions, or database roles.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L31](../src/april_repro/database.py#L31) | class | <code>DatabaseError(RuntimeError)</code> | A deliberately credential-free error safe to show in the terminal. |
| [L35](../src/april_repro/database.py#L35) | function/method | <code>connection_environment(project_root: Path) -&gt; dict[str, str]</code> | Read a small dotenv subset as literal text; process environment wins. |
| [L59](../src/april_repro/database.py#L59) | function/method | <code>connection_status(env: dict[str, str]) -&gt; dict[str, object]</code> |  |
| [L67](../src/april_repro/database.py#L67) | function/method | <code>_statement_body(sql: str) -&gt; str</code> | Check reviewed templates, not arbitrary untrusted SQL or function effects. |
| [L147](../src/april_repro/database.py#L147) | function/method | <code>validate_timeout(timeout_ms: int) -&gt; None</code> |  |
| [L152](../src/april_repro/database.py#L152) | function/method | <code>wrap_readonly_query(sql: str, timeout_ms: int=10000, max_rows: int &#124; None=None, work_mem_mb: int &#124; None=None) -&gt; str</code> |  |
| [L173](../src/april_repro/database.py#L173) | function/method | <code>_safe_error(stderr: str) -&gt; str</code> |  |
| [L196](../src/april_repro/database.py#L196) | class | <code>PsqlClient()</code> |  |
| [L197](../src/april_repro/database.py#L197) | function/method | <code>PsqlClient.__init__(self, project_root: Path, timeout_ms: int=10000)</code> |  |
| [L212](../src/april_repro/database.py#L212) | function/method | <code>PsqlClient.query(self, filename: str) -&gt; tuple[str, list[dict[str, str]], str]</code> |  |
| [L224](../src/april_repro/database.py#L224) | function/method | <code>PsqlClient._execute_wrapped(self, wrapped: str) -&gt; tuple[str, list[dict[str, str]]]</code> | Internal transport for wrappers constructed from reviewed templates. |

<a id="module-4caccf92a702"></a>

## src/april_repro/decision_features.py

[Open source](../src/april_repro/decision_features.py)

Source module docstring:

> Assemble pre-decision features separately from outcomes and cohort labels.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L27](../src/april_repro/decision_features.py#L27) | function/method | <code>parse_time(value: str) -&gt; datetime</code> |  |
| [L37](../src/april_repro/decision_features.py#L37) | function/method | <code>decision_keys(rows: list[dict[str, str]]) -&gt; list[tuple[str, str, str, str]]</code> | Validate identifiers before rendering private, bounded VALUES inputs. |
| [L54](../src/april_repro/decision_features.py#L54) | function/method | <code>render_decision_query(template: str, rows: list[dict[str, str]]) -&gt; str</code> |  |
| [L66](../src/april_repro/decision_features.py#L66) | function/method | <code>_indexed(rows: list[dict[str, str]], expected: dict, kind: str) -&gt; dict</code> |  |
| [L83](../src/april_repro/decision_features.py#L83) | function/method | <code>_feature_value(name: str, value: str &#124; None)</code> |  |
| [L104](../src/april_repro/decision_features.py#L104) | function/method | <code>assemble_features(decisions, contexts, medications, groups)</code> | No outcome, action, diagnosis label or future time enters features.csv. |

<a id="module-0083d978557e"></a>

## src/april_repro/decision_opportunities.py

[Open source](../src/april_repro/decision_opportunities.py)

Source module docstring:

> Four-hour observational decisions; no patient data or database side effects.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L20](../src/april_repro/decision_opportunities.py#L20) | class | <code>Event()</code> |  |
| [L34](../src/april_repro/decision_opportunities.py#L34) | class | <code>Interval()</code> |  |
| [L41](../src/april_repro/decision_opportunities.py#L41) | function/method | <code>timestamp(value: str) -&gt; datetime &#124; None</code> |  |
| [L45](../src/april_repro/decision_opportunities.py#L45) | function/method | <code>number(value: str) -&gt; Decimal &#124; None</code> |  |
| [L55](../src/april_repro/decision_opportunities.py#L55) | function/method | <code>overlap(interval: Interval, start: datetime, end: datetime) -&gt; Decimal</code> |  |
| [L60](../src/april_repro/decision_opportunities.py#L60) | function/method | <code>normalize_events(rows: list[dict[str, str]], task: str) -&gt; list[Event]</code> |  |
| [L105](../src/april_repro/decision_opportunities.py#L105) | function/method | <code>selected_admissions(events: list[Event]) -&gt; list[tuple[str, str]]</code> | Treatment-source population, not a population selected by final action. |
| [L111](../src/april_repro/decision_opportunities.py#L111) | function/method | <code>infusion_intervals(events: list[Event], task: str) -&gt; list[Interval]</code> | Closed start/confirmation/stop blocks; unresolved streams remain unknown. |
| [L176](../src/april_repro/decision_opportunities.py#L176) | function/method | <code>sodium_action(dose: Decimal) -&gt; int &#124; None</code> | Zero is absence, never a rounded small positive amount. No top clipping. |
| [L185](../src/april_repro/decision_opportunities.py#L185) | function/method | <code>build_decisions(opportunities: list[dict[str, str]], events: list[Event], task: str) -&gt; tuple[list[dict], dict]</code> |  |

<a id="module-1ecee1237dcb"></a>

## src/april_repro/estimators.py

[Open source](../src/april_repro/estimators.py)

Source module docstring:

> Evaluate the direct-method equation; do not choose a training protocol. APRIL Section 3.3 (PDF p. 5) specifies a learned linear reward model but omits important fitting/encoding details. This module takes supplied action values and target-policy probabilities; it does not silently pick those missing details, clone a policy, or train a reward model.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L19](../src/april_repro/estimators.py#L19) | function/method | <code>_finite_matrix(values: Iterable[Iterable[Real]], name: str) -&gt; List[List[float]]</code> |  |
| [L31](../src/april_repro/estimators.py#L31) | function/method | <code>_validate_probabilities(probabilities: List[float], name: str) -&gt; None</code> |  |
| [L43](../src/april_repro/estimators.py#L43) | function/method | <code>direct_method(policy_probabilities: Iterable[Iterable[Real]], action_values: Iterable[Iterable[Real]], context_weights: Optional[Iterable[Real]]=None) -&gt; float</code> | Return sum_s d0(s) sum_a pi(a&#124;s) Q(s,a). |

<a id="module-713cf24c3006"></a>

## src/april_repro/evidence.py

[Open source](../src/april_repro/evidence.py)

Source module docstring:

> Verify saved aggregate-query evidence against the current reviewed templates. This proves local content consistency, not source authenticity, a shared database snapshot, or scientific cohort validity. No database connection.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L18](../src/april_repro/evidence.py#L18) | function/method | <code>_digest(data: bytes) -&gt; str</code> |  |
| [L22](../src/april_repro/evidence.py#L22) | function/method | <code>_local_file(directory: Path, filename: str) -&gt; Path</code> |  |
| [L31](../src/april_repro/evidence.py#L31) | function/method | <code>verify_profile_evidence(root: Path) -&gt; dict</code> |  |

<a id="module-26b5dde6800b"></a>

## src/april_repro/full_decisions.py

[Open source](../src/april_repro/full_decisions.py)

Source module docstring:

> Repartition complete source events before constructing common opportunities.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L12](../src/april_repro/full_decisions.py#L12) | function/method | <code>event_owner(event: Event, count: int=20) -&gt; int</code> | Use the final identity, including the distinct order-identity blocker. |
| [L19](../src/april_repro/full_decisions.py#L19) | function/method | <code>event_json(event: Event) -&gt; str</code> |  |
| [L27](../src/april_repro/full_decisions.py#L27) | function/method | <code>event_from_json(text: str) -&gt; Event</code> |  |
| [L35](../src/april_repro/full_decisions.py#L35) | class | <code>DecisionCounts()</code> | Count without retaining every excluded opportunity in memory. |
| [L37](../src/april_repro/full_decisions.py#L37) | function/method | <code>DecisionCounts.__init__(self)</code> |  |
| [L44](../src/april_repro/full_decisions.py#L44) | function/method | <code>DecisionCounts.add(self, rows)</code> |  |
| [L58](../src/april_repro/full_decisions.py#L58) | function/method | <code>DecisionCounts.summary(self)</code> |  |
| [L73](../src/april_repro/full_decisions.py#L73) | function/method | <code>combine_owner_summaries(summaries)</code> | Owners partition by subject, so patient/admission totals are additive. |

<a id="module-168653ace03c"></a>

## src/april_repro/full_vocabulary_audit.py

[Open source](../src/april_repro/full_vocabulary_audit.py)

Source module docstring:

> Offline, value-safe audit for the private Query-201 vocabulary artifact. This module never opens a database connection. It independently recomputes the normalization, lexical review classification, Query-200 subset membership, and all published aggregate counters from the saved private dictionary. Audit output contains only counts, hashes, boolean controls, and safe check names.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L58](../src/april_repro/full_vocabulary_audit.py#L58) | class | <code>SourceSpec()</code> |  |
| [L164](../src/april_repro/full_vocabulary_audit.py#L164) | class | <code>AuditContractError(RuntimeError)</code> | A safe audit failure that contains no controlled-vocabulary value. |
| [L168](../src/april_repro/full_vocabulary_audit.py#L168) | class | <code>Checks()</code> |  |
| [L169](../src/april_repro/full_vocabulary_audit.py#L169) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L173](../src/april_repro/full_vocabulary_audit.py#L173) | function/method | <code>Checks.require(self, condition: bool, name: str) -&gt; None</code> |  |
| [L180](../src/april_repro/full_vocabulary_audit.py#L180) | function/method | <code>Checks.check(self, condition: bool, name: str) -&gt; None</code> |  |
| [L186](../src/april_repro/full_vocabulary_audit.py#L186) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L190](../src/april_repro/full_vocabulary_audit.py#L190) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L198](../src/april_repro/full_vocabulary_audit.py#L198) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L202](../src/april_repro/full_vocabulary_audit.py#L202) | function/method | <code>_read_unique_json(path: Path, limit: int, label: str) -&gt; dict[str, Any]</code> |  |
| [L207](../src/april_repro/full_vocabulary_audit.py#L207) | function/method | <code>_read_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L226](../src/april_repro/full_vocabulary_audit.py#L226) | function/method | <code>_safe_file(directory: Path, filename: Any, label: str) -&gt; Path</code> |  |
| [L240](../src/april_repro/full_vocabulary_audit.py#L240) | function/method | <code>_independent_classify(raw: str) -&gt; dict[str, Any]</code> |  |
| [L280](../src/april_repro/full_vocabulary_audit.py#L280) | function/method | <code>_expected_lineage(*, summary: bool=False, manifest: bool=False) -&gt; dict[str, Any]</code> |  |
| [L294](../src/april_repro/full_vocabulary_audit.py#L294) | function/method | <code>_load_q200(root: Path, checks: Checks) -&gt; dict[str, set[str]]</code> |  |
| [L356](../src/april_repro/full_vocabulary_audit.py#L356) | function/method | <code>_audit_preregistration(root: Path, manifest: Mapping[str, Any], checks: Checks) -&gt; None</code> |  |
| [L400](../src/april_repro/full_vocabulary_audit.py#L400) | function/method | <code>_audit_public_payload(payload: Mapping[str, Any], private_values: set[str], label: str, checks: Checks) -&gt; None</code> |  |
| [L407](../src/april_repro/full_vocabulary_audit.py#L407) | function/method | <code>_audit_public_payload.walk(value: Any) -&gt; None</code> |  |
| [L432](../src/april_repro/full_vocabulary_audit.py#L432) | function/method | <code>_audit_dictionary(discovery: Mapping[str, Any], summary: Mapping[str, Any], q200_vocabulary: Mapping[str, set[str]], checks: Checks) -&gt; tuple[dict[str, int], dict[str, int], set[str]]</code> |  |
| [L679](../src/april_repro/full_vocabulary_audit.py#L679) | function/method | <code>_template_body(raw: bytes) -&gt; str</code> |  |
| [L686](../src/april_repro/full_vocabulary_audit.py#L686) | function/method | <code>_audit_executed_sql(root: Path, raw: bytes, stages: Mapping[str, Any], checks: Checks) -&gt; None</code> |  |
| [L735](../src/april_repro/full_vocabulary_audit.py#L735) | function/method | <code>_audit_manifest_and_files(root: Path, directory: Path, manifest: Mapping[str, Any], discovery_raw: bytes, summary_raw: bytes, executed_raw: bytes, source_totals: Mapping[str, int], source_negatives: Mapping[str, int], checks: Checks) -&gt; None</code> |  |
| [L886](../src/april_repro/full_vocabulary_audit.py#L886) | function/method | <code>audit_artifact(directory: Path, root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Audit one Query-201 directory and write a private aggregate-only report. |

<a id="module-0d4381fe7079"></a>

## src/april_repro/full_vocabulary_discovery.py

[Open source](../src/april_repro/full_vocabulary_discovery.py)

Source module docstring:

> Fail-closed Query-201 discovery of the four complete medication vocabularies. The database portion consists only of four reviewed SELECT statements. They run in one persistent PostgreSQL session and one REPEATABLE READ READ ONLY transaction. Database values remain in memory until an explicit rollback has been observed and psql has exited with status zero. The full vocabulary and the executed SQL are then written as private files; the summary and manifest contain counts and hashes only.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L67](../src/april_repro/full_vocabulary_discovery.py#L67) | class | <code>StageSpec()</code> |  |
| [L171](../src/april_repro/full_vocabulary_discovery.py#L171) | function/method | <code>_now() -&gt; str</code> |  |
| [L175](../src/april_repro/full_vocabulary_discovery.py#L175) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L179](../src/april_repro/full_vocabulary_discovery.py#L179) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L187](../src/april_repro/full_vocabulary_discovery.py#L187) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L191](../src/april_repro/full_vocabulary_discovery.py#L191) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L214](../src/april_repro/full_vocabulary_discovery.py#L214) | function/method | <code>_remove_values(paths: list[Path]) -&gt; bool</code> |  |
| [L223](../src/april_repro/full_vocabulary_discovery.py#L223) | function/method | <code>_unique_json(payload: bytes, label: str, byte_limit: int) -&gt; dict[str, Any]</code> |  |
| [L227](../src/april_repro/full_vocabulary_discovery.py#L227) | function/method | <code>_unique_json.unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L244](../src/april_repro/full_vocabulary_discovery.py#L244) | function/method | <code>_snapshot_token(value: Any, label: str) -&gt; str</code> |  |
| [L257](../src/april_repro/full_vocabulary_discovery.py#L257) | function/method | <code>_decode_frame(frame: bytes, spec: StageSpec) -&gt; dict[str, Any]</code> |  |
| [L277](../src/april_repro/full_vocabulary_discovery.py#L277) | function/method | <code>_validate_stage_payload(payload: bytes, spec: StageSpec) -&gt; dict[str, Any]</code> |  |
| [L342](../src/april_repro/full_vocabulary_discovery.py#L342) | function/method | <code>_assert_one_snapshot(payloads: Mapping[str, Mapping[str, Any]]) -&gt; str</code> |  |
| [L354](../src/april_repro/full_vocabulary_discovery.py#L354) | function/method | <code>_local_artifact(directory: Path, filename: Any, label: str) -&gt; Path</code> |  |
| [L368](../src/april_repro/full_vocabulary_discovery.py#L368) | function/method | <code>_validate_hash_map(value: Mapping[str, str]) -&gt; dict[str, str]</code> |  |
| [L378](../src/april_repro/full_vocabulary_discovery.py#L378) | function/method | <code>load_q200_evidence(root: Path, *, manifest_path: Path &#124; None=None, expected_hashes: Mapping[str, str]=EXPECTED_Q200_HASHES, expected_value_counts: Mapping[str, int]=EXPECTED_Q200_VALUE_COUNTS, expected_audit_checks: int=EXPECTED_Q200_AUDIT_CHECKS) -&gt; dict[str, Any]</code> | Load the accepted Query-200 bundle without exposing dictionary values. |
| [L516](../src/april_repro/full_vocabulary_discovery.py#L516) | function/method | <code>classify_name(raw_name: str) -&gt; dict[str, Any]</code> | Classify one controlled name into a neutral review stratum. |
| [L571](../src/april_repro/full_vocabulary_discovery.py#L571) | function/method | <code>build_private_discovery(payloads: Mapping[str, Mapping[str, Any]], q200: Mapping[str, Any], *, snapshot_token: str) -&gt; dict[str, Any]</code> | Create the full private review dictionary and enforce exact Q200 subset. |
| [L654](../src/april_repro/full_vocabulary_discovery.py#L654) | function/method | <code>build_aggregate_summary(discovery: Mapping[str, Any]) -&gt; dict[str, Any]</code> | Reduce the private dictionary to a value-free conservation summary. |
| [L774](../src/april_repro/full_vocabulary_discovery.py#L774) | function/method | <code>_assert_value_free_public_payload(payload: Mapping[str, Any], raw_values: list[str]) -&gt; None</code> | Reject accidental raw-name fields or byte-for-byte name disclosure. |
| [L780](../src/april_repro/full_vocabulary_discovery.py#L780) | function/method | <code>_assert_value_free_public_payload.walk(value: Any) -&gt; None</code> |  |
| [L801](../src/april_repro/full_vocabulary_discovery.py#L801) | function/method | <code>_success_payloads(discovery: dict[str, Any], summary: dict[str, Any], executed_sql: bytes, *, rollback_confirmed: bool, psql_returncode: int &#124; None) -&gt; tuple[bytes, bytes, bytes]</code> | Serialization gate: private values cannot cross it before clean rollback. |
| [L836](../src/april_repro/full_vocabulary_discovery.py#L836) | function/method | <code>_session_preamble() -&gt; str</code> |  |
| [L847](../src/april_repro/full_vocabulary_discovery.py#L847) | function/method | <code>_initial_stage(spec: StageSpec) -&gt; dict[str, Any]</code> |  |
| [L860](../src/april_repro/full_vocabulary_discovery.py#L860) | function/method | <code>_record_frame(session: _PersistentPsql, stage: dict[str, Any], control: str, marker: str) -&gt; bytes</code> |  |
| [L883](../src/april_repro/full_vocabulary_discovery.py#L883) | function/method | <code>run_full_vocabulary_discovery(root: Path) -&gt; dict[str, Any]</code> | Run Query 201 and return only terminal-safe metadata. |

<a id="module-6bf4b49657a8"></a>

## src/april_repro/linear_training_candidate.py

[Open source](../src/april_repro/linear_training_candidate.py)

Source module docstring:

> Small, dependency-free weighted OLS candidate for synthetic validation. This module does not select features, add an intercept, scale an input design semantically, or define a clinical cohort. Callers supply the complete design matrix and explicit weights and rank tolerance. Internal column equilibration is reversed before coefficients are returned. The solver uses column-pivoted, reorthogonalized modified Gram--Schmidt QR, not normal equations. It rejects a numerically rank-deficient design instead of computing a pseudoinverse. This is a small synthetic numerical candidate; it is not a production rank-deficiency policy or a frozen experiment method.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L25](../src/april_repro/linear_training_candidate.py#L25) | function/method | <code>_number(value: object) -&gt; float</code> |  |
| [L34](../src/april_repro/linear_training_candidate.py#L34) | function/method | <code>_items(values: object) -&gt; tuple</code> |  |
| [L40](../src/april_repro/linear_training_candidate.py#L40) | function/method | <code>_matrix(design: object) -&gt; tuple[tuple[float, ...], ...]</code> |  |
| [L51](../src/april_repro/linear_training_candidate.py#L51) | function/method | <code>_finite(value: float) -&gt; float</code> |  |
| [L57](../src/april_repro/linear_training_candidate.py#L57) | function/method | <code>_dot(left: Iterable[float], right: Iterable[float]) -&gt; float</code> |  |
| [L61](../src/april_repro/linear_training_candidate.py#L61) | function/method | <code>_norm(values: list[float]) -&gt; float</code> |  |
| [L65](../src/april_repro/linear_training_candidate.py#L65) | function/method | <code>_remove_projection(vector: list[float], direction: list[float], coefficient: float) -&gt; list[float]</code> |  |
| [L72](../src/april_repro/linear_training_candidate.py#L72) | function/method | <code>_unscale(value: float, norm: float, scale: float) -&gt; float</code> | Compute value / (norm * scale) without a large intermediate product. |
| [L90](../src/april_repro/linear_training_candidate.py#L90) | class | <code>LinearFit()</code> | OLS coefficients in the caller's original design-column order. |
| [L101](../src/april_repro/linear_training_candidate.py#L101) | function/method | <code>LinearFit.__post_init__(self) -&gt; None</code> |  |
| [L116](../src/april_repro/linear_training_candidate.py#L116) | function/method | <code>LinearFit.predict(self, design: Iterable[Iterable[float]]) -&gt; tuple[float, ...]</code> | Predict from a nonempty matrix with exactly &#96;&#96;n_columns&#96;&#96; columns. |
| [L127](../src/april_repro/linear_training_candidate.py#L127) | function/method | <code>fit_ols(design: Iterable[Iterable[float]], rewards: Iterable[float], *, sample_weights: Iterable[float], rank_tolerance: float) -&gt; LinearFit</code> | Fit explicit-design weighted least squares to rewards in &#96;&#96;[0, 1]&#96;&#96;. |

<a id="module-89f15ee96967"></a>

## src/april_repro/llm_credentials.py

[Open source](../src/april_repro/llm_credentials.py)

Source module docstring:

> Read explicitly selected dotenv credentials without executing shell code.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L11](../src/april_repro/llm_credentials.py#L11) | function/method | <code>load_provider_env(path, *, environ=None)</code> |  |

<a id="module-02e1efc2bbf5"></a>

## src/april_repro/llm_five_packet.py

[Open source](../src/april_repro/llm_five_packet.py)

Source module docstring:

> Expand a validated two-model offline packet without selecting new events. Only the small source packet and its provenance files are read. Clinical CSVs are neither opened nor reselected. Factual labels stay outside API payloads.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L26](../src/april_repro/llm_five_packet.py#L26) | function/method | <code>_encoded(value)</code> |  |
| [L31](../src/april_repro/llm_five_packet.py#L31) | function/method | <code>_sha(path)</code> |  |
| [L39](../src/april_repro/llm_five_packet.py#L39) | function/method | <code>_check_file(path, digest, bindings)</code> |  |
| [L49](../src/april_repro/llm_five_packet.py#L49) | function/method | <code>_jsonl(path)</code> |  |
| [L54](../src/april_repro/llm_five_packet.py#L54) | function/method | <code>_consumer_key(consumer, mode)</code> |  |
| [L65](../src/april_repro/llm_five_packet.py#L65) | function/method | <code>_summary(records, labels, pairs)</code> |  |
| [L76](../src/april_repro/llm_five_packet.py#L76) | function/method | <code>_load_source(directory)</code> |  |
| [L181](../src/april_repro/llm_five_packet.py#L181) | function/method | <code>_code_identity()</code> |  |
| [L191](../src/april_repro/llm_five_packet.py#L191) | function/method | <code>_write_private(path, rows)</code> |  |
| [L198](../src/april_repro/llm_five_packet.py#L198) | function/method | <code>prepare_five_packet(source_packet_directory, output_directory, *, config_path)</code> | Return a complete private five-model manifest; never issue network calls. |

<a id="module-608a4ffa1e9b"></a>

## src/april_repro/llm_five_requests.py

[Open source](../src/april_repro/llm_five_requests.py)

Source module docstring:

> Fixed five-provider adapters for existing APRIL prompts; no network access. The three additional providers are a user-selected adapted replication, not the paper's historical model set. Only &#96;&#96;payload&#96;&#96; is sent; identity and transport provenance remain in the private ledger. Endpoint selection never falls back to another region. Provider names/aliases do not establish account availability.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L85](../src/april_repro/llm_five_requests.py#L85) | function/method | <code>_sha(value)</code> |  |
| [L108](../src/april_repro/llm_five_requests.py#L108) | function/method | <code>_registry(version)</code> |  |
| [L122](../src/april_repro/llm_five_requests.py#L122) | function/method | <code>_hash_value(value)</code> |  |
| [L126](../src/april_repro/llm_five_requests.py#L126) | function/method | <code>_same(actual, expected, message)</code> |  |
| [L132](../src/april_repro/llm_five_requests.py#L132) | function/method | <code>_check_common(record, *, five)</code> |  |
| [L184](../src/april_repro/llm_five_requests.py#L184) | function/method | <code>validate_base_request(record)</code> | Verify an old two-OpenAI request without reading its patient source files. |
| [L200](../src/april_repro/llm_five_requests.py#L200) | function/method | <code>_request_identity(record)</code> |  |
| [L205](../src/april_repro/llm_five_requests.py#L205) | function/method | <code>build_five_request(base_record, model_key, *, registry_version=REGISTRY_VERSION)</code> | Reuse the verified prompt verbatim; bind provider routing and parameters. |
| [L235](../src/april_repro/llm_five_requests.py#L235) | function/method | <code>validate_request(record)</code> | Reject routing/parameter/identity drift before any transport operation. |
| [L257](../src/april_repro/llm_five_requests.py#L257) | function/method | <code>validate_five_config(path)</code> | Check the small offline config against the executed registry, not prose. |

<a id="module-daa8c4217aac"></a>

## src/april_repro/llm_formal_plan.py

[Open source](../src/april_repro/llm_formal_plan.py)

Source module docstring:

> Build a private formal annotation plan without network or credential access. Clinical selection and prompt identity are reused verbatim from the pilot. The larger cell limit extends deterministic prefixes; it does not resample or use observed outcomes. Existing annotations are reusable only after raw receipt revalidation. This plan is not an executable legacy review packet or a result.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L30](../src/april_repro/llm_formal_plan.py#L30) | function/method | <code>load_config(path, *, selection_config_path, model_config_path)</code> |  |
| [L57](../src/april_repro/llm_formal_plan.py#L57) | function/method | <code>_code_identity()</code> |  |
| [L70](../src/april_repro/llm_formal_plan.py#L70) | function/method | <code>_jsonl(path)</code> |  |
| [L74](../src/april_repro/llm_formal_plan.py#L74) | function/method | <code>verify_pilot(summary_directory, packet_directories)</code> | Recompute saved pilot summary from its original requests and raw receipts. |
| [L143](../src/april_repro/llm_formal_plan.py#L143) | function/method | <code>_cells(dataset, selected, counts)</code> | Only identity, roles and folds are used to describe support and prefixes. |
| [L186](../src/april_repro/llm_formal_plan.py#L186) | function/method | <code>prepare_formal_plan(input_directories, output_directory, *, config_path, selection_config_path, model_config_path, pilot_summary_directory=None, pilot_packet_directories=())</code> | Prepare one or both tasks. No provider requests, credentials, or fitting. |

<a id="module-a9f9c1822e86"></a>

## src/april_repro/llm_formal_recovery.py

[Open source](../src/april_repro/llm_formal_recovery.py)

Source module docstring:

> Explicitly recorded recovery after an acknowledged account credit interruption. Completed quota failures remain failed observations. Only untouched request IDs may be sent; the original run plan, transport, retry policy and payloads remain unchanged. Every continuation binds its predecessor and extra execution source.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L32](../src/april_repro/llm_formal_recovery.py#L32) | function/method | <code>recovery_source_hashes()</code> |  |
| [L41](../src/april_repro/llm_formal_recovery.py#L41) | function/method | <code>_quota_evidence(output, plan, rid, *, max_retries)</code> |  |
| [L71](../src/april_repro/llm_formal_recovery.py#L71) | function/method | <code>_verify_segment(output, segment_id, plan, visited)</code> |  |
| [L124](../src/april_repro/llm_formal_recovery.py#L124) | function/method | <code>verify_recovery_provenance(output_directory, plan=None)</code> | Verify the closed continuation chain before collecting its annotations. |
| [L143](../src/april_repro/llm_formal_recovery.py#L143) | function/method | <code>_begin_segment(output, plan, recovery_id, acknowledged, binding)</code> |  |
| [L197](../src/april_repro/llm_formal_recovery.py#L197) | function/method | <code>run_recovery(plan, output_directory, *, provider_settings, environ, runtime_sha256, recovery_id, acknowledged_quota_stop_ids, max_retries=2, timeout=120, workers=5, stop_event=None, send=None, sleeper=None)</code> | Resume untouched requests after exactly acknowledged exhausted-credit errors. |
| [L282](../src/april_repro/llm_formal_recovery.py#L282) | function/method | <code>run_recovery.aggregate(status='active')</code> |  |
| [L297](../src/april_repro/llm_formal_recovery.py#L297) | function/method | <code>run_recovery.publish()</code> |  |
| [L315](../src/april_repro/llm_formal_recovery.py#L315) | function/method | <code>run_recovery.worker(model)</code> |  |
| [L339](../src/april_repro/llm_formal_recovery.py#L339) | function/method | <code>run_recovery.worker.before_attempt(number)</code> |  |
| [L346](../src/april_repro/llm_formal_recovery.py#L346) | function/method | <code>run_recovery.worker.after_attempt(number, receipt, raw, decision)</code> |  |

<a id="module-2bca12e30c6b"></a>

## src/april_repro/llm_formal_recovery_v2.py

[Open source](../src/april_repro/llm_formal_recovery_v2.py)

Source module docstring:

> Versioned recovery for exact acknowledged OpenAI and Moonshot credit stops. The v1 source stays immutable; legacy segments use its original verifier. Completed quota failures remain failed observations. Only untouched request IDs may be sent; the original run plan, transport, retry policy and payloads remain unchanged. Every continuation binds its predecessor and extra execution source.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L39](../src/april_repro/llm_formal_recovery_v2.py#L39) | function/method | <code>recovery_source_hashes()</code> |  |
| [L49](../src/april_repro/llm_formal_recovery_v2.py#L49) | function/method | <code>_quota_evidence(output, plan, rid, *, max_retries)</code> |  |
| [L86](../src/april_repro/llm_formal_recovery_v2.py#L86) | function/method | <code>_verify_segment(output, segment_id, plan, visited)</code> |  |
| [L141](../src/april_repro/llm_formal_recovery_v2.py#L141) | function/method | <code>verify_recovery_provenance(output_directory, plan=None)</code> | Verify the closed continuation chain before collecting its annotations. |
| [L160](../src/april_repro/llm_formal_recovery_v2.py#L160) | function/method | <code>_begin_segment(output, plan, recovery_id, acknowledged, binding)</code> |  |
| [L216](../src/april_repro/llm_formal_recovery_v2.py#L216) | function/method | <code>run_recovery(plan, output_directory, *, provider_settings, environ, runtime_sha256, recovery_id, acknowledged_quota_stop_ids, max_retries=2, timeout=120, workers=5, stop_event=None, send=None, sleeper=None)</code> | Resume untouched requests after exactly acknowledged exhausted-credit errors. |
| [L301](../src/april_repro/llm_formal_recovery_v2.py#L301) | function/method | <code>run_recovery.aggregate(status='active')</code> |  |
| [L316](../src/april_repro/llm_formal_recovery_v2.py#L316) | function/method | <code>run_recovery.publish()</code> |  |
| [L334](../src/april_repro/llm_formal_recovery_v2.py#L334) | function/method | <code>run_recovery.worker(model)</code> |  |
| [L358](../src/april_repro/llm_formal_recovery_v2.py#L358) | function/method | <code>run_recovery.worker.before_attempt(number)</code> |  |
| [L365](../src/april_repro/llm_formal_recovery_v2.py#L365) | function/method | <code>run_recovery.worker.after_attempt(number, receipt, raw, decision)</code> |  |

<a id="module-0aa74a2178bd"></a>

## src/april_repro/llm_formal_run.py

[Open source](../src/april_repro/llm_formal_run.py)

Source module docstring:

> Durable, resumable execution of the explicitly approved formal annotation plan. The plan/pilot are revalidated locally before network access. Unknown interrupted attempts are held, never automatically posted again. Each model has one worker.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L29](../src/april_repro/llm_formal_run.py#L29) | function/method | <code>_sha(path)</code> |  |
| [L37](../src/april_repro/llm_formal_run.py#L37) | function/method | <code>_json(path)</code> |  |
| [L41](../src/april_repro/llm_formal_run.py#L41) | function/method | <code>_encoded(value)</code> |  |
| [L45](../src/april_repro/llm_formal_run.py#L45) | function/method | <code>_sync_directory(path)</code> |  |
| [L53](../src/april_repro/llm_formal_run.py#L53) | function/method | <code>private_write(path, raw, *, replace=False)</code> | Persist bytes plus directory entry, with atomic replacement for status. |
| [L76](../src/april_repro/llm_formal_run.py#L76) | class | <code>FormalPlan()</code> |  |
| [L86](../src/april_repro/llm_formal_run.py#L86) | function/method | <code>_check_bound(info)</code> |  |
| [L91](../src/april_repro/llm_formal_run.py#L91) | function/method | <code>load_formal_plan(directory)</code> | Verify immutable formal payloads, their inputs, and original pilot raw data. |
| [L195](../src/april_repro/llm_formal_run.py#L195) | function/method | <code>source_hashes()</code> |  |
| [L208](../src/april_repro/llm_formal_run.py#L208) | function/method | <code>_stem(rid, number)</code> |  |
| [L212](../src/april_repro/llm_formal_run.py#L212) | function/method | <code>_result(rid, attempts)</code> |  |
| [L221](../src/april_repro/llm_formal_run.py#L221) | function/method | <code>verify_request_result(folder, record, *, result=None, max_retries=2)</code> | Validate annotation against every durable raw response, including retry policy. |
| [L246](../src/april_repro/llm_formal_run.py#L246) | function/method | <code>inspect_request(folder, record, *, max_retries=2)</code> | Read state without writing. Recover only a complete terminal receipt chain. |
| [L285](../src/april_repro/llm_formal_run.py#L285) | function/method | <code>exclusive_run_lock(output_directory, formal_manifest_sha256=None, *, lock_root=None)</code> | Prevent parallel writers, including different outputs for the same plan. |
| [L325](../src/april_repro/llm_formal_run.py#L325) | function/method | <code>_provider_stop(result)</code> |  |
| [L329](../src/april_repro/llm_formal_run.py#L329) | function/method | <code>run_formal_plan(plan, output_directory, *, provider_settings, environ, runtime_sha256, max_retries=2, timeout=120, send=None, sleeper=None, workers=5, stop_event=None)</code> | Execute immutable new requests; cache reuse and safe resume make no POSTs. |
| [L416](../src/april_repro/llm_formal_run.py#L416) | function/method | <code>run_formal_plan.aggregate(status='active')</code> |  |
| [L430](../src/april_repro/llm_formal_run.py#L430) | function/method | <code>run_formal_plan.publish()</code> |  |
| [L438](../src/april_repro/llm_formal_run.py#L438) | function/method | <code>run_formal_plan.worker(model)</code> |  |
| [L462](../src/april_repro/llm_formal_run.py#L462) | function/method | <code>run_formal_plan.worker.before_attempt(number)</code> |  |
| [L469](../src/april_repro/llm_formal_run.py#L469) | function/method | <code>run_formal_plan.worker.after_attempt(number, receipt, raw, decision)</code> |  |

<a id="module-1293ad6e43cc"></a>

## src/april_repro/llm_formal_summary.py

[Open source](../src/april_repro/llm_formal_summary.py)

Source module docstring:

> Offline formal annotations, with strict raw replay and full planned denominators. No API calls or clinical feature reconstruction occur here; the bound input files are read only to verify their hashes. Cached pilot replies use the formal request consumers, so an overlapping split never loses its annotation. Completed calls, outstanding attempts and usable annotation budgets are separate.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L28](../src/april_repro/llm_formal_summary.py#L28) | function/method | <code>_ids(value, label)</code> |  |
| [L35](../src/april_repro/llm_formal_summary.py#L35) | function/method | <code>_cached(plan)</code> |  |
| [L51](../src/april_repro/llm_formal_summary.py#L51) | function/method | <code>_new_results(plan, run_directory)</code> |  |
| [L142](../src/april_repro/llm_formal_summary.py#L142) | function/method | <code>_group(rows)</code> |  |
| [L167](../src/april_repro/llm_formal_summary.py#L167) | function/method | <code>summarize_formal_run(plan_directory, run_directory=None)</code> | Revalidate inputs and return (aggregate summary, private annotation rows). |
| [L257](../src/april_repro/llm_formal_summary.py#L257) | function/method | <code>write_summary(plan_directory, run_directory, output_directory)</code> | Write immutable private results only after raw and request validation. |

<a id="module-2bc9a927608a"></a>

## src/april_repro/llm_packet.py

[Open source](../src/april_repro/llm_packet.py)

Source module docstring:

> Prepare small private APRIL review packets locally; never call an API. Selection uses only event identity, action, role and fold. Full artifacts are validated by ClinicalDataset; selected raw inputs are then joined and hash-read again without retaining the unselected CSV rows. Labels remain a separate file.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L29](../src/april_repro/llm_packet.py#L29) | function/method | <code>_sha(path)</code> |  |
| [L37](../src/april_repro/llm_packet.py#L37) | function/method | <code>_encoded(value)</code> |  |
| [L42](../src/april_repro/llm_packet.py#L42) | function/method | <code>_limit(value)</code> |  |
| [L48](../src/april_repro/llm_packet.py#L48) | function/method | <code>load_config(path, *, pairs_per_cell=None)</code> | Check operational fields against the actual fixed request builder. |
| [L97](../src/april_repro/llm_packet.py#L97) | function/method | <code>select_pairs(dataset, *, seed, pairs_per_cell=5)</code> | Bottom-K SHA256(seed,task,split,mode,event,action), O(6*K) heap space. |
| [L146](../src/april_repro/llm_packet.py#L146) | function/method | <code>_selected_contexts(directory, dataset, selected)</code> |  |
| [L152](../src/april_repro/llm_packet.py#L152) | function/method | <code>_selected_contexts.check_identity(row, index)</code> |  |
| [L202](../src/april_repro/llm_packet.py#L202) | function/method | <code>_code_identity()</code> |  |
| [L212](../src/april_repro/llm_packet.py#L212) | function/method | <code>_write_private(path, rows)</code> |  |
| [L219](../src/april_repro/llm_packet.py#L219) | function/method | <code>prepare_packet(input_directory, output_directory, *, config_path, pairs_per_cell=None)</code> | Create one task's offline pilot artifact, or fail without a complete manifest. |

<a id="module-ca6695d905df"></a>

## src/april_repro/llm_predictions.py

[Open source](../src/april_repro/llm_predictions.py)

Source module docstring:

> Strict, offline LLM lab-response parsing and factual-only evaluation. No model calls, retries, repair, prose extraction, or raw-response rewriting. The caller preserves and hashes raw replies in private storage. Invalid replies remain in coverage denominators; F1 and lab errors use valid predictions only. Observed labels belong to this evaluator, never to the prompt constructor.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L37](../src/april_repro/llm_predictions.py#L37) | class | <code>ParsedPrediction()</code> |  |
| [L47](../src/april_repro/llm_predictions.py#L47) | function/method | <code>ParsedPrediction.to_dict(self)</code> |  |
| [L55](../src/april_repro/llm_predictions.py#L55) | class | <code>_RejectedJSON(ValueError)</code> |  |
| [L59](../src/april_repro/llm_predictions.py#L59) | function/method | <code>_task(task)</code> |  |
| [L64](../src/april_repro/llm_predictions.py#L64) | function/method | <code>_pairs(pairs)</code> |  |
| [L73](../src/april_repro/llm_predictions.py#L73) | function/method | <code>_constant(_value)</code> |  |
| [L77](../src/april_repro/llm_predictions.py#L77) | function/method | <code>parse_prediction_response(raw_response, task, *, allow_json_fence=True)</code> | Parse exactly the two paper response keys, returning explicit invalids. |
| [L84](../src/april_repro/llm_predictions.py#L84) | function/method | <code>parse_prediction_response.invalid(reason)</code> |  |
| [L143](../src/april_repro/llm_predictions.py#L143) | function/method | <code>_nonempty(value, label)</code> |  |
| [L149](../src/april_repro/llm_predictions.py#L149) | function/method | <code>_observed(value)</code> |  |
| [L161](../src/april_repro/llm_predictions.py#L161) | function/method | <code>_validated_prediction(prediction, task)</code> |  |
| [L195](../src/april_repro/llm_predictions.py#L195) | function/method | <code>evaluate_factual_predictions(task, records)</code> | Evaluate one model/protocol batch; individual rendered prompt hashes vary. |

<a id="module-c325abcc9d9c"></a>

## src/april_repro/llm_receipts.py

[Open source](../src/april_repro/llm_receipts.py)

Source module docstring:

> Offline validation of OpenAI-compatible chat completion receipts. The caller verifies the request ledger, stores/hashes the original response, and handles transport. This module never calls a service, retries, repairs a reply, or parses reasoning text as a lab prediction. The 4 MiB response bound and strict single completed choice are implementation choices, not paper facts. Only a separately supplied observed label enters the factual evaluation bridge.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L21](../src/april_repro/llm_receipts.py#L21) | class | <code>_InvalidJSON(ValueError)</code> |  |
| [L25](../src/april_repro/llm_receipts.py#L25) | function/method | <code>_pairs(pairs)</code> |  |
| [L34](../src/april_repro/llm_receipts.py#L34) | function/method | <code>_constant(_value)</code> |  |
| [L38](../src/april_repro/llm_receipts.py#L38) | function/method | <code>_body(response_body)</code> |  |
| [L69](../src/april_repro/llm_receipts.py#L69) | function/method | <code>_text(value, field)</code> |  |
| [L75](../src/april_repro/llm_receipts.py#L75) | function/method | <code>_request(record)</code> |  |
| [L103](../src/april_repro/llm_receipts.py#L103) | function/method | <code>_numeric_usage(value)</code> | Keep numeric token accounting, never arbitrary response or credential text. |
| [L120](../src/april_repro/llm_receipts.py#L120) | function/method | <code>normalize_receipt(record, response_body, *, http_status=200)</code> | Validate one receipt and parse only its completed assistant content. |
| [L140](../src/april_repro/llm_receipts.py#L140) | function/method | <code>normalize_receipt.invalid(reason)</code> |  |
| [L197](../src/april_repro/llm_receipts.py#L197) | function/method | <code>factual_record_from_receipt(record, receipt, *, observed_lab_value)</code> | Bridge a factual receipt to evaluate_factual_predictions without dropping failures. |

<a id="module-7685f35bf1bc"></a>

## src/april_repro/llm_requests.py

[Open source](../src/april_repro/llm_requests.py)

Source module docstring:

> Local APRIL prompt/request construction; no network or patient-file access. The paper prints a placeholder UpToDate paragraph, not its source text. The guidance below is explicitly reconstructed from Appendix A / Figure 5. Snapshot IDs, zero-action timing, missing-value wording and request limits are project choices, not recovered historical settings. Only &#96;&#96;payload&#96;&#96; is an API body; the surrounding identity and provenance must remain in the private ledger.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L91](../src/april_repro/llm_requests.py#L91) | function/method | <code>_json_sha(value)</code> |  |
| [L108](../src/april_repro/llm_requests.py#L108) | function/method | <code>_number(value, field, *, minimum=0, maximum=None, inclusive=False)</code> |  |
| [L122](../src/april_repro/llm_requests.py#L122) | function/method | <code>_display(number)</code> |  |
| [L126](../src/april_repro/llm_requests.py#L126) | function/method | <code>_missing(value)</code> |  |
| [L130](../src/april_repro/llm_requests.py#L130) | function/method | <code>_action(value, task)</code> |  |
| [L139](../src/april_repro/llm_requests.py#L139) | function/method | <code>_features(features)</code> |  |
| [L162](../src/april_repro/llm_requests.py#L162) | function/method | <code>render_prompt(*, task, action, features, pre_lab_value=None, pre_lab_hours_before_anchor=None)</code> | Render only declared pretreatment values; identities/labels are not inputs. |
| [L204](../src/april_repro/llm_requests.py#L204) | function/method | <code>_sha_identity(value, field)</code> |  |
| [L210](../src/april_repro/llm_requests.py#L210) | function/method | <code>build_request(*, event_id_sha256, input_manifest_sha256, mode, task, observed_action, action, model_key, features, pre_lab_value=None, pre_lab_hours_before_anchor=None)</code> | Return a private ledger record with a separately isolated API payload. |

<a id="module-6e5d08e5ef8e"></a>

## src/april_repro/llm_retries.py

[Open source](../src/april_repro/llm_retries.py)

Source module docstring:

> Bounded transient retries without changing a prompt or selecting its answer. The caller must persist an attempt before this module waits or issues another POST. Completed refusals, truncations, and prediction parsing failures are terminal. Repeated POSTs can be billed even when a prior response was lost.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L32](../src/april_repro/llm_retries.py#L32) | function/method | <code>_terminal_service_error(raw)</code> | Classify only the service error envelope, never generated answer text. |
| [L51](../src/april_repro/llm_retries.py#L51) | function/method | <code>retry_decision(receipt, raw, *, attempt_number, max_retries=2, uniform=None)</code> | Return a sanitized decision; Retry-After is a minimum, never shortened. |
| [L89](../src/april_repro/llm_retries.py#L89) | function/method | <code>execute_with_retries(record, provider_settings, *, before_attempt, after_attempt, environ=None, timeout=120, max_retries=2, send=None, sleeper=None, uniform=None)</code> | Return one annotation result plus all attempt references. |

<a id="module-e566e92033ec"></a>

## src/april_repro/llm_run_summary.py

[Open source](../src/april_repro/llm_run_summary.py)

Source module docstring:

> Offline pilot annotation collection; no provider calls or clinical CSV reads. One request contributes one final annotation even if transport was retried. Missing requests remain invalid in coverage denominators. Factual evaluation uses the existing Appendix A bins and only valid predictions for F1/lab errors. These small review packets are not the formal 500-annotation experiment.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L27](../src/april_repro/llm_run_summary.py#L27) | function/method | <code>_encoded(value)</code> |  |
| [L31](../src/april_repro/llm_run_summary.py#L31) | function/method | <code>_sha(raw)</code> |  |
| [L35](../src/april_repro/llm_run_summary.py#L35) | function/method | <code>_read_json(path)</code> |  |
| [L40](../src/april_repro/llm_run_summary.py#L40) | function/method | <code>_file(folder, name)</code> |  |
| [L49](../src/april_repro/llm_run_summary.py#L49) | function/method | <code>_packet(directory)</code> |  |
| [L100](../src/april_repro/llm_run_summary.py#L100) | function/method | <code>_receipt(folder, request, attempt, number)</code> |  |
| [L130](../src/april_repro/llm_run_summary.py#L130) | function/method | <code>_annotation(folder, request, result)</code> |  |
| [L157](../src/april_repro/llm_run_summary.py#L157) | function/method | <code>_usage(value, result, prefix='')</code> |  |
| [L167](../src/april_repro/llm_run_summary.py#L167) | function/method | <code>summarize_runs(packet_directories, run_directories)</code> | Return (aggregate summary, private annotation rows) for all packet requests. |
| [L298](../src/april_repro/llm_run_summary.py#L298) | function/method | <code>write_summary(packet_directories, run_directories, output_directory)</code> | Validate first, then persist private parsed annotations and aggregate metrics. |

<a id="module-2ca648dcc141"></a>

## src/april_repro/llm_transport.py

[Open source](../src/april_repro/llm_transport.py)

Source module docstring:

> Single-attempt HTTPS transport for the five explicitly configured models. No automatic retry, redirect, model replacement or credential persistence. Patient requests require the actual provider's configured data-handling state. This module is tested with injected synthetic transports, not live services.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L28](../src/april_repro/llm_transport.py#L28) | class | <code>_NoRedirect(request.HTTPRedirectHandler)</code> |  |
| [L29](../src/april_repro/llm_transport.py#L29) | function/method | <code>_NoRedirect.redirect_request(self, req, fp, code, msg, headers, newurl)</code> |  |
| [L33](../src/april_repro/llm_transport.py#L33) | function/method | <code>_retry_after_seconds(headers, received_at)</code> | Extract a numeric wait only; never persist arbitrary response headers. |
| [L50](../src/april_repro/llm_transport.py#L50) | function/method | <code>_read_body(response, buffer)</code> |  |
| [L60](../src/april_repro/llm_transport.py#L60) | function/method | <code>preflight(record, provider_settings=None, *, environ=None)</code> | Return only non-secret local readiness; this does not probe an account. |
| [L86](../src/april_repro/llm_transport.py#L86) | function/method | <code>execute_once(record, provider_settings, *, environ=None, timeout=120, opener=None)</code> | Send one validated request after readiness checks; return receipt and raw bytes. |

<a id="module-2c071c4cc67b"></a>

## src/april_repro/mapping_preflight.py

[Open source](../src/april_repro/mapping_preflight.py)

Source module docstring:

> Fail-closed D005 five-field mapping-preflight runner. Five reviewed SELECT statements enumerate exact typed values and frequencies in one PostgreSQL REPEATABLE READ READ ONLY transaction. Raw route, product and NDC values remain in memory until an explicit rollback and clean psql exit have both been observed. Public metadata contains aggregate counts and whole-set hashes only.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L73](../src/april_repro/mapping_preflight.py#L73) | class | <code>StageSpec()</code> |  |
| [L126](../src/april_repro/mapping_preflight.py#L126) | function/method | <code>_now() -&gt; str</code> |  |
| [L130](../src/april_repro/mapping_preflight.py#L130) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L134](../src/april_repro/mapping_preflight.py#L134) | function/method | <code>_classification_runtime() -&gt; dict[str, str]</code> |  |
| [L141](../src/april_repro/mapping_preflight.py#L141) | function/method | <code>_implementation_bundle(root: Path, paths: tuple[str, ...]) -&gt; dict[str, Any]</code> | Hash one ordered implementation bundle with path/content lengths. |
| [L175](../src/april_repro/mapping_preflight.py#L175) | function/method | <code>implementation_bundles(root: Path) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L182](../src/april_repro/mapping_preflight.py#L182) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L190](../src/april_repro/mapping_preflight.py#L190) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L194](../src/april_repro/mapping_preflight.py#L194) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L217](../src/april_repro/mapping_preflight.py#L217) | function/method | <code>_remove_values(paths: list[Path]) -&gt; bool</code> |  |
| [L226](../src/april_repro/mapping_preflight.py#L226) | function/method | <code>_snapshot_token(value: Any, label: str) -&gt; str</code> |  |
| [L239](../src/april_repro/mapping_preflight.py#L239) | function/method | <code>_strict_uint(value: str, label: str, maximum: int) -&gt; int</code> |  |
| [L248](../src/april_repro/mapping_preflight.py#L248) | function/method | <code>_value_substate(raw_value: str) -&gt; str</code> |  |
| [L256](../src/april_repro/mapping_preflight.py#L256) | function/method | <code>typed_set_sha256(source_field: str, records: list[Mapping[str, Any]]) -&gt; str</code> | Hash a field's typed distinct set using the preregistered byte protocol. |
| [L315](../src/april_repro/mapping_preflight.py#L315) | function/method | <code>_decode_frame(frame: bytes, spec: StageSpec) -&gt; dict[str, Any]</code> | Decode a row-streamed base64 CSV frame without logging raw values. |
| [L447](../src/april_repro/mapping_preflight.py#L447) | function/method | <code>_assert_one_snapshot(payloads: Mapping[str, Mapping[str, Any]]) -&gt; str</code> |  |
| [L459](../src/april_repro/mapping_preflight.py#L459) | function/method | <code>_validate_preregistration_gate(report: Any) -&gt; dict[str, Any]</code> |  |
| [L493](../src/april_repro/mapping_preflight.py#L493) | function/method | <code>build_private_preflight(payloads: Mapping[str, Mapping[str, Any]], preregistered: Mapping[str, Any], *, snapshot_token: str) -&gt; dict[str, Any]</code> |  |
| [L559](../src/april_repro/mapping_preflight.py#L559) | function/method | <code>build_aggregate_summary(private: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L680](../src/april_repro/mapping_preflight.py#L680) | function/method | <code>_assert_value_free_public_payload(payload: Mapping[str, Any], raw_values: list[str]) -&gt; None</code> |  |
| [L691](../src/april_repro/mapping_preflight.py#L691) | function/method | <code>_assert_value_free_public_payload.walk(value: Any) -&gt; None</code> |  |
| [L710](../src/april_repro/mapping_preflight.py#L710) | function/method | <code>_success_payloads(private: dict[str, Any], summary: dict[str, Any], executed_sql: bytes, *, rollback_confirmed: bool, psql_returncode: int &#124; None) -&gt; tuple[bytes, bytes, bytes]</code> |  |
| [L747](../src/april_repro/mapping_preflight.py#L747) | function/method | <code>_session_preamble() -&gt; str</code> |  |
| [L757](../src/april_repro/mapping_preflight.py#L757) | function/method | <code>_stage_control(statement: str, marker: str, *, first: bool) -&gt; str</code> |  |
| [L768](../src/april_repro/mapping_preflight.py#L768) | function/method | <code>_initial_stage(spec: StageSpec) -&gt; dict[str, Any]</code> |  |
| [L781](../src/april_repro/mapping_preflight.py#L781) | function/method | <code>_record_frame(session: _PersistentPsql, stage: dict[str, Any], control: str, marker: str) -&gt; bytes</code> |  |
| [L801](../src/april_repro/mapping_preflight.py#L801) | function/method | <code>run_mapping_preflight(root: Path) -&gt; dict[str, Any]</code> | Execute the five-field preflight and return terminal-safe metadata only. |

<a id="module-11bd06e9a8c6"></a>

## src/april_repro/mapping_preflight_audit.py

[Open source](../src/april_repro/mapping_preflight_audit.py)

Source module docstring:

> Independent offline audit for the D005 five-field mapping preflight. The auditor uses only Python's standard library and never opens a database connection. It deliberately reimplements typed-value classification, set hashing, implementation-bundle hashing, SQL-control reconstruction, and JSON validation rather than importing the production runner.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L39](../src/april_repro/mapping_preflight_audit.py#L39) | class | <code>SourceSpec()</code> |  |
| [L181](../src/april_repro/mapping_preflight_audit.py#L181) | class | <code>AuditContractError(RuntimeError)</code> | A fail-closed audit error whose message contains no private value. |
| [L185](../src/april_repro/mapping_preflight_audit.py#L185) | class | <code>Checks()</code> |  |
| [L186](../src/april_repro/mapping_preflight_audit.py#L186) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L191](../src/april_repro/mapping_preflight_audit.py#L191) | function/method | <code>Checks.require(self, condition: bool, name: str) -&gt; None</code> |  |
| [L200](../src/april_repro/mapping_preflight_audit.py#L200) | function/method | <code>Checks.check(self, condition: bool, name: str) -&gt; None</code> |  |
| [L208](../src/april_repro/mapping_preflight_audit.py#L208) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L212](../src/april_repro/mapping_preflight_audit.py#L212) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L220](../src/april_repro/mapping_preflight_audit.py#L220) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L224](../src/april_repro/mapping_preflight_audit.py#L224) | function/method | <code>_runtime_contract() -&gt; dict[str, str]</code> |  |
| [L231](../src/april_repro/mapping_preflight_audit.py#L231) | function/method | <code>_read_unique_json(path: Path, byte_limit: int, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L239](../src/april_repro/mapping_preflight_audit.py#L239) | function/method | <code>_read_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L258](../src/april_repro/mapping_preflight_audit.py#L258) | function/method | <code>_safe_file(directory: Path, filename: Any, label: str) -&gt; Path</code> |  |
| [L272](../src/april_repro/mapping_preflight_audit.py#L272) | function/method | <code>_safe_relative_path(value: Any, label: str) -&gt; str</code> |  |
| [L281](../src/april_repro/mapping_preflight_audit.py#L281) | function/method | <code>_implementation_bundle(root: Path, paths: tuple[str, ...]) -&gt; dict[str, Any]</code> | Independently hash an ordered path/content bundle. |
| [L311](../src/april_repro/mapping_preflight_audit.py#L311) | function/method | <code>_all_bundles(root: Path) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L315](../src/april_repro/mapping_preflight_audit.py#L315) | function/method | <code>_typed_set_sha256(source_field: str, records: list[Mapping[str, Any]]) -&gt; str</code> | Recompute the registered hash without using runner code. |
| [L365](../src/april_repro/mapping_preflight_audit.py#L365) | function/method | <code>_nonnull_substate(raw: str) -&gt; str</code> |  |
| [L373](../src/april_repro/mapping_preflight_audit.py#L373) | function/method | <code>_audit_config(root: Path, manifest: Mapping[str, Any], bundles: Mapping[str, Mapping[str, Any]], checks: Checks) -&gt; tuple[dict[str, Any], str]</code> |  |
| [L470](../src/april_repro/mapping_preflight_audit.py#L470) | function/method | <code>_audit_manifest_bundles(manifest: Mapping[str, Any], bundles: Mapping[str, Mapping[str, Any]], checks: Checks) -&gt; None</code> |  |
| [L504](../src/april_repro/mapping_preflight_audit.py#L504) | function/method | <code>_audit_public_payload(payload: Mapping[str, Any], private_values: set[str], label: str, checks: Checks) -&gt; None</code> |  |
| [L513](../src/april_repro/mapping_preflight_audit.py#L513) | function/method | <code>_audit_public_payload.walk(value: Any) -&gt; None</code> |  |
| [L545](../src/april_repro/mapping_preflight_audit.py#L545) | function/method | <code>_audit_private_and_summary(private: Mapping[str, Any], summary: Mapping[str, Any], *, config_sha: str, checks: Checks) -&gt; tuple[dict[str, dict[str, Any]], set[str]]</code> |  |
| [L761](../src/april_repro/mapping_preflight_audit.py#L761) | function/method | <code>_template_body(raw: bytes, label: str) -&gt; str</code> |  |
| [L771](../src/april_repro/mapping_preflight_audit.py#L771) | function/method | <code>_visible_sql(text: str, label: str) -&gt; str</code> | Mask comments and quoted strings for a conservative read-only scan. |
| [L821](../src/april_repro/mapping_preflight_audit.py#L821) | function/method | <code>_audit_sql_template(root: Path, spec: SourceSpec, checks: Checks) -&gt; bytes</code> |  |
| [L859](../src/april_repro/mapping_preflight_audit.py#L859) | function/method | <code>_audit_executed_sql(root: Path, raw: bytes, stages: Mapping[str, Any], checks: Checks) -&gt; None</code> |  |
| [L914](../src/april_repro/mapping_preflight_audit.py#L914) | function/method | <code>_audit_manifest_and_files(root: Path, directory: Path, manifest: Mapping[str, Any], private_raw: bytes, summary_raw: bytes, executed_raw: bytes, source_results: Mapping[str, Mapping[str, Any]], bundles: Mapping[str, Mapping[str, Any]], checks: Checks) -&gt; None</code> |  |
| [L1091](../src/april_repro/mapping_preflight_audit.py#L1091) | function/method | <code>_write_audit(path: Path, result: Mapping[str, Any]) -&gt; None</code> |  |
| [L1115](../src/april_repro/mapping_preflight_audit.py#L1115) | function/method | <code>audit_artifact(directory: Path, root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Audit a persisted preflight without connecting to PostgreSQL. |

<a id="module-9e47e978bedf"></a>

## src/april_repro/metrics.py

[Open source](../src/april_repro/metrics.py)

Source module docstring:

> Transparent metrics for the APRIL reproduction, using standard Python. RMSE is sqrt(mean(squared signed errors)), never mean absolute error. Entropy is the empirical marginal action entropy in natural-log units; it is not a measure of annotation quality or conditional coverage.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L15](../src/april_repro/metrics.py#L15) | function/method | <code>weighted_f1(true_labels: Iterable[int], predicted_labels: Iterable[int], *, num_classes: int) -&gt; float</code> | Support-weighted multiclass F1 with explicit fixed class count. |
| [L58](../src/april_repro/metrics.py#L58) | function/method | <code>lab_weighted_f1(observed: Iterable[Real], predicted: Iterable[Real], task: Task) -&gt; float</code> | Bin observed and predicted labs using Appendix A, then compute F1. |
| [L70](../src/april_repro/metrics.py#L70) | function/method | <code>_paired_errors(estimates: Iterable[Real], references: Union[Real, Iterable[Real]]) -&gt; List[float]</code> |  |
| [L89](../src/april_repro/metrics.py#L89) | function/method | <code>rmse(estimates: Iterable[Real], references: Union[Real, Iterable[Real]]) -&gt; float</code> | Root mean squared error against one reference or paired references. |
| [L98](../src/april_repro/metrics.py#L98) | function/method | <code>bias(estimates: Iterable[Real], references: Union[Real, Iterable[Real]]) -&gt; float</code> | Mean signed error, with sign estimate minus reference. |
| [L104](../src/april_repro/metrics.py#L104) | function/method | <code>marginal_entropy(action_counts: Iterable[int]) -&gt; float</code> | Compute -sum(p * ln(p)) from nonnegative integer action counts. |

<a id="module-970d896b54ed"></a>

## src/april_repro/outcomes.py

[Open source](../src/april_repro/outcomes.py)

Source module docstring:

> Synthetic oracle for the proposed D003 potassium outcome rule. This module implements &#96;&#96;k-observed-outcome-v1-proposed&#96;&#96;. It is a project proposal whose upstream episode, action, decision-anchor, and non-ICU rules remain unresolved; accepting a synthetic event here does not construct a formal study label or recover the paper authors' undisclosed selector. The primary clock is the eMAR administration-record anchor. The prompt-only proxy end (dose / 10 mEq per hour) and proxy target (three hours later) never participate in this selector.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L28](../src/april_repro/outcomes.py#L28) | class | <code>PotassiumLabRow()</code> | One synthetic serum-potassium result row considered by the oracle. |
| [L44](../src/april_repro/outcomes.py#L44) | class | <code>PotassiumOutcomeSelection()</code> | Auditable result of applying the proposed rule to one synthetic event. |
| [L61](../src/april_repro/outcomes.py#L61) | function/method | <code>PotassiumOutcomeSelection.accepted(self) -&gt; bool</code> | Whether this event satisfies the proposal, not a formal protocol. |
| [L67](../src/april_repro/outcomes.py#L67) | function/method | <code>PotassiumOutcomeSelection.normalized_value(self) -&gt; float &#124; None</code> | Expose a value only when the complete proposed rule accepts it. |
| [L73](../src/april_repro/outcomes.py#L73) | function/method | <code>_require_datetime(value: object, name: str) -&gt; datetime</code> |  |
| [L79](../src/april_repro/outcomes.py#L79) | function/method | <code>_compare(left: datetime, right: datetime, *, names: str) -&gt; int</code> | Compare datetimes while turning naive/aware mismatches into clear input errors. |
| [L92](../src/april_repro/outcomes.py#L92) | function/method | <code>_normalized_unit(value: object) -&gt; str &#124; None</code> |  |
| [L99](../src/april_repro/outcomes.py#L99) | function/method | <code>_finite_number(value: object) -&gt; float &#124; None</code> |  |
| [L111](../src/april_repro/outcomes.py#L111) | function/method | <code>_row_sort_key(row: PotassiumLabRow) -&gt; tuple[object, ...]</code> | Canonical presentation order that never consults the source row ID. |
| [L131](../src/april_repro/outcomes.py#L131) | function/method | <code>select_proposed_potassium_outcome(anchor: datetime, labs: Iterable[PotassiumLabRow], *, additional_treatment_times: Iterable[datetime]=(), same_anchor_distinct_event: bool=False) -&gt; PotassiumOutcomeSelection</code> | Apply the proposed D003-K rule to one synthetic positive-dose event. |

<a id="module-9df8b81c9ad0"></a>

## src/april_repro/paired_training_candidate.py

[Open source](../src/april_repro/paired_training_candidate.py)

Source module docstring:

> Synthetic candidate for paired DM/DM+ reward training (D006/D007/D011). The caller supplies the complete design matrix, action order, source/protocol, weights and fixed evaluation policy/d0. No clinical schema, policy fitting, preprocessing, bootstrap, clipping or formal experiment is implemented here.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L20](../src/april_repro/paired_training_candidate.py#L20) | class | <code>FactualRow()</code> |  |
| [L30](../src/april_repro/paired_training_candidate.py#L30) | class | <code>AnnotationRow()</code> |  |
| [L42](../src/april_repro/paired_training_candidate.py#L42) | class | <code>EvaluationRow()</code> |  |
| [L51](../src/april_repro/paired_training_candidate.py#L51) | class | <code>BudgetResult()</code> |  |
| [L65](../src/april_repro/paired_training_candidate.py#L65) | class | <code>PairedCandidateRun()</code> |  |
| [L76](../src/april_repro/paired_training_candidate.py#L76) | function/method | <code>_identifier(value: object) -&gt; str</code> |  |
| [L82](../src/april_repro/paired_training_candidate.py#L82) | function/method | <code>_sequence(value: Iterable) -&gt; tuple</code> |  |
| [L91](../src/april_repro/paired_training_candidate.py#L91) | function/method | <code>_design(value: Iterable, width: int) -&gt; tuple[float, ...]</code> |  |
| [L98](../src/april_repro/paired_training_candidate.py#L98) | function/method | <code>_reward_weight(reward: float, weight: float) -&gt; tuple[float, float]</code> |  |
| [L106](../src/april_repro/paired_training_candidate.py#L106) | function/method | <code>_weight_sum(weights: Iterable[float]) -&gt; float</code> |  |
| [L116](../src/april_repro/paired_training_candidate.py#L116) | function/method | <code>fit_paired_candidate(factual: Iterable[FactualRow], annotations: Iterable[AnnotationRow], evaluation: Iterable[EvaluationRow], *, actions: Iterable[int], budgets: Iterable[int], design_columns: Iterable[str], annotation_source_id: str, annotation_protocol_id: str, rank_tolerance: float) -&gt; PairedCandidateRun</code> | Fit one baseline and single-source DM+ models on nested pool prefixes. |
| [L224](../src/april_repro/paired_training_candidate.py#L224) | function/method | <code>fit_paired_candidate.evaluate(model: LinearFit) -&gt; float</code> |  |

<a id="module-c8930f1332a5"></a>

## src/april_repro/paper_alignment.py

[Open source](../src/april_repro/paper_alignment.py)

Source module docstring:

> Supplemental checks of disclosed APRIL facts, outside the frozen CLI. This checks draft configuration metadata, not clinical data or experiment fidelity. The original validator and its frozen execution snapshot stay intact.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L26](../src/april_repro/paper_alignment.py#L26) | function/method | <code>_exact_members(value: object, expected: frozenset[str]) -&gt; bool</code> |  |
| [L35](../src/april_repro/paper_alignment.py#L35) | function/method | <code>_exact_number(value: object, expected: int) -&gt; bool</code> |  |
| [L41](../src/april_repro/paper_alignment.py#L41) | function/method | <code>validate_paper_alignment(config: dict) -&gt; list[str]</code> | Return old draft-validation errors plus field-specific paper-fact errors. |

<a id="module-69b6401a28a8"></a>

## src/april_repro/preregistration.py

[Open source](../src/april_repro/preregistration.py)

Source module docstring:

> Machine checks for research sub-protocols that remain short of a full freeze.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L164](../src/april_repro/preregistration.py#L164) | function/method | <code>_sha256(path: Path) -&gt; str</code> |  |
| [L168](../src/april_repro/preregistration.py#L168) | function/method | <code>_implementation_bundle(root: Path, paths: tuple[Path, ...]) -&gt; dict</code> | Hash a fixed ordered code bundle with unambiguous path/content framing. |
| [L198](../src/april_repro/preregistration.py#L198) | function/method | <code>read_potassium_outcome_preregistration(root: Path) -&gt; dict</code> |  |
| [L203](../src/april_repro/preregistration.py#L203) | function/method | <code>validate_potassium_outcome_preregistration(config: dict) -&gt; list[str]</code> | Reject silent changes to the proposed D003 potassium outcome contract. |
| [L207](../src/april_repro/preregistration.py#L207) | function/method | <code>validate_potassium_outcome_preregistration.expect(container: dict, key: str, value: object, prefix: str) -&gt; None</code> |  |
| [L385](../src/april_repro/preregistration.py#L385) | function/method | <code>potassium_outcome_preregistration_report(root: Path) -&gt; dict</code> | Validate the lock and, when present locally, its ignored evidence files. |
| [L419](../src/april_repro/preregistration.py#L419) | function/method | <code>read_potassium_source_discovery_preregistration(root: Path) -&gt; dict</code> |  |
| [L424](../src/april_repro/preregistration.py#L424) | function/method | <code>validate_potassium_source_discovery_preregistration(config: dict) -&gt; list[str]</code> | Reject drift in the proposed D005 potassium source-discovery contract. |
| [L428](../src/april_repro/preregistration.py#L428) | function/method | <code>validate_potassium_source_discovery_preregistration.expect(container: dict, key: str, value: object, prefix: str) -&gt; None</code> |  |
| [L687](../src/april_repro/preregistration.py#L687) | function/method | <code>potassium_source_discovery_preregistration_report(root: Path) -&gt; dict</code> | Validate the D005 discovery proposal and all locally present evidence. |
| [L722](../src/april_repro/preregistration.py#L722) | function/method | <code>read_potassium_product_mapping_preregistration(root: Path) -&gt; dict</code> |  |
| [L727](../src/april_repro/preregistration.py#L727) | function/method | <code>validate_potassium_product_mapping_preregistration(config: dict) -&gt; list[str]</code> | Reject drift in the proposed D005 product-mapping contract. |
| [L731](../src/april_repro/preregistration.py#L731) | function/method | <code>validate_potassium_product_mapping_preregistration.expect(container: dict, key: str, value: object, prefix: str) -&gt; None</code> |  |
| [L1300](../src/april_repro/preregistration.py#L1300) | function/method | <code>potassium_product_mapping_preregistration_report(root: Path) -&gt; dict</code> | Validate the mapping proposal and hashes of its nine existing inputs. |
| [L1352](../src/april_repro/preregistration.py#L1352) | function/method | <code>read_potassium_mapping_preflight_preregistration(root: Path) -&gt; dict</code> |  |
| [L1357](../src/april_repro/preregistration.py#L1357) | function/method | <code>validate_potassium_mapping_preflight_preregistration(config: dict) -&gt; list[str]</code> | Reject drift in the proposed five-field mapping preflight contract. |
| [L1361](../src/april_repro/preregistration.py#L1361) | function/method | <code>validate_potassium_mapping_preflight_preregistration.expect(container: dict, key: str, value: object, prefix: str) -&gt; None</code> |  |
| [L1365](../src/april_repro/preregistration.py#L1365) | function/method | <code>validate_potassium_mapping_preflight_preregistration.table(name: str) -&gt; dict</code> |  |
| [L1727](../src/april_repro/preregistration.py#L1727) | function/method | <code>potassium_mapping_preflight_preregistration_report(root: Path) -&gt; dict</code> | Validate preflight boundaries, evidence, and executable input hashes. |

<a id="module-4ee0e1ad8121"></a>

## src/april_repro/product_mapping_contract.py

[Open source](../src/april_repro/product_mapping_contract.py)

Source module docstring:

> Pure reducers for the proposed D005 potassium product-mapping contract. These functions do not read MIMIC, decide product identities, or enable a source policy. They make the preregistered three-state logic executable so Query 202 cannot silently choose favorable evidence across memberships or physical components.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L39](../src/april_repro/product_mapping_contract.py#L39) | function/method | <code>_semantic_decision(value: Mapping[str, Any]) -&gt; dict[str, str]</code> |  |
| [L51](../src/april_repro/product_mapping_contract.py#L51) | function/method | <code>uncertain_semantics() -&gt; dict[str, str]</code> |  |
| [L55](../src/april_repro/product_mapping_contract.py#L55) | function/method | <code>route_category(*, has_iv: bool, has_noniv: bool, has_unknown: bool) -&gt; str</code> | Return the complete three-presence-bit direct-detail route partition. |
| [L62](../src/april_repro/product_mapping_contract.py#L62) | function/method | <code>event_route_status(category: str) -&gt; str</code> | Map a direct-detail route category to supported/refuted/uncertain. |
| [L73](../src/april_repro/product_mapping_contract.py#L73) | function/method | <code>reduce_component_semantics(membership_decisions: Sequence[Mapping[str, Any]], *, mapping_group_ids: Sequence[str &#124; None] &#124; None=None, group_decision: Mapping[str, Any] &#124; None=None) -&gt; dict[str, str]</code> | Reduce semantic memberships without cross-membership cherry-picking. |
| [L111](../src/april_repro/product_mapping_contract.py#L111) | function/method | <code>reduce_component_domains(semantics: Mapping[str, Any], *, event_route: str, identity_chain: str, component_role: str) -&gt; dict[str, str]</code> | Compute component-level focal and interference statuses. |
| [L161](../src/april_repro/product_mapping_contract.py#L161) | function/method | <code>reduce_head_domains(components: Sequence[Mapping[str, Any]]) -&gt; dict[str, str]</code> | Reduce physical components to event-head focal/interference domains. |
| [L209](../src/april_repro/product_mapping_contract.py#L209) | function/method | <code>enumerate_route_partition() -&gt; tuple[str, ...]</code> | Return all eight categories through the production reducer. |

<a id="module-276293bd2195"></a>

## src/april_repro/product_review_ledger.py

[Open source](../src/april_repro/product_review_ledger.py)

Source module docstring:

> Private Query-201 to D005 product-semantic review ledger workflow. This module is deliberately offline. It copies the accepted Query-201 raw vocabulary memberships into a private review ledger without making a product identity decision. Query-201 review strata remain lineage only: every source membership is retained and all five semantic dimensions start &#96;&#96;uncertain&#96;&#96;. The validator also supports later reviewed copies of the ledger, while keeping the exact Query-201 membership universe fixed. It never treats a SQL NULL as text. A literal text value such as &#96;&#96;"NULL"&#96;&#96; remains an ordinary non-NULL value only when that exact string was present in Query 201.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L113](../src/april_repro/product_review_ledger.py#L113) | class | <code>ProductReviewLedgerError(RuntimeError)</code> | A value-safe contract failure. |
| [L117](../src/april_repro/product_review_ledger.py#L117) | class | <code>SourceSpec(tuple)</code> | Small immutable source description without a dataclass dependency. |
| [L122](../src/april_repro/product_review_ledger.py#L122) | function/method | <code>SourceSpec.__new__(cls, key: str, field: str, evidence_path: str)</code> |  |
| [L126](../src/april_repro/product_review_ledger.py#L126) | function/method | <code>SourceSpec.key(self) -&gt; str</code> |  |
| [L130](../src/april_repro/product_review_ledger.py#L130) | function/method | <code>SourceSpec.field(self) -&gt; str</code> |  |
| [L134](../src/april_repro/product_review_ledger.py#L134) | function/method | <code>SourceSpec.evidence_path(self) -&gt; str</code> |  |
| [L191](../src/april_repro/product_review_ledger.py#L191) | function/method | <code>_now() -&gt; str</code> |  |
| [L195](../src/april_repro/product_review_ledger.py#L195) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L199](../src/april_repro/product_review_ledger.py#L199) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L207](../src/april_repro/product_review_ledger.py#L207) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L211](../src/april_repro/product_review_ledger.py#L211) | function/method | <code>_strict_json_bytes(payload: bytes, label: str) -&gt; dict[str, Any]</code> |  |
| [L215](../src/april_repro/product_review_ledger.py#L215) | function/method | <code>_strict_json_bytes.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L223](../src/april_repro/product_review_ledger.py#L223) | function/method | <code>_strict_json_bytes.invalid_constant(_: str) -&gt; None</code> |  |
| [L241](../src/april_repro/product_review_ledger.py#L241) | function/method | <code>_read_private_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L250](../src/april_repro/product_review_ledger.py#L250) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L270](../src/april_repro/product_review_ledger.py#L270) | function/method | <code>_json_payload(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L277](../src/april_repro/product_review_ledger.py#L277) | function/method | <code>_hash_parts(parts: Sequence[str]) -&gt; str</code> | Hash exact UTF-8 parts with an unsigned 64-bit length prefix. |
| [L289](../src/april_repro/product_review_ledger.py#L289) | function/method | <code>_valid_timestamp(value: Any) -&gt; bool</code> |  |
| [L299](../src/april_repro/product_review_ledger.py#L299) | function/method | <code>_validated_raw(value: Any, label: str) -&gt; str</code> |  |
| [L311](../src/april_repro/product_review_ledger.py#L311) | function/method | <code>_validate_q201_discovery(discovery: Mapping[str, Any], *, expected_source_counts: Mapping[str, int], expected_q200_counts: Mapping[str, int]) -&gt; dict[str, Any]</code> |  |
| [L408](../src/april_repro/product_review_ledger.py#L408) | function/method | <code>_typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> | Recompute the preflight typed-set hash from exact typed values. |
| [L447](../src/april_repro/product_review_ledger.py#L447) | function/method | <code>_validate_preflight_product_other(private_values: Mapping[str, Any], *, expected_nonnull_count: int=EXPECTED_PRODUCT_OTHER_NONNULL, expected_typed_set_sha256: str=PRODUCT_OTHER_TYPED_SET_SHA256) -&gt; dict[str, Any]</code> |  |
| [L541](../src/april_repro/product_review_ledger.py#L541) | function/method | <code>_validate_mapping_contract(root: Path) -&gt; dict[str, str]</code> |  |
| [L591](../src/april_repro/product_review_ledger.py#L591) | function/method | <code>load_accepted_inputs(root: Path) -&gt; tuple[dict[str, Any], dict[str, Any], dict[str, Any]]</code> | Load accepted Q201, preflight product-other and mapping contracts. |
| [L697](../src/april_repro/product_review_ledger.py#L697) | function/method | <code>_initial_semantics() -&gt; dict[str, dict[str, Any]]</code> |  |
| [L704](../src/april_repro/product_review_ledger.py#L704) | function/method | <code>build_initial_review_ledger(q201_discovery: Mapping[str, Any], preflight_private_values: Mapping[str, Any], input_hashes: Mapping[str, str], *, expected_source_counts: Mapping[str, int]=EXPECTED_SOURCE_COUNTS, expected_q200_counts: Mapping[str, int]=EXPECTED_Q200_COUNTS, expected_product_other_nonnull: int=EXPECTED_PRODUCT_OTHER_NONNULL, created_at_utc: str &#124; None=None) -&gt; dict[str, Any]</code> | Build the all-uncertain Q201 plus product-other review universe. |
| [L749](../src/april_repro/product_review_ledger.py#L749) | function/method | <code>build_initial_review_ledger.append_record(*, spec: SourceSpec, raw: str, source_type: str, origin_component: str, q201_review_stratum: str &#124; None, q201_q200_member: bool &#124; None, preflight_nonnull_substate: str &#124; None, preflight_exact_row_count: int &#124; None) -&gt; None</code> |  |
| [L872](../src/april_repro/product_review_ledger.py#L872) | function/method | <code>_validate_string_list(value: Any, label: str) -&gt; list[str]</code> |  |
| [L880](../src/april_repro/product_review_ledger.py#L880) | function/method | <code>_validate_review_record(record: Any, spec: SourceSpec, expected_raw: str, expected_lineage: Mapping[str, Any], source_type: str, index: int, *, require_initial: bool) -&gt; tuple[str, str]</code> |  |
| [L994](../src/april_repro/product_review_ledger.py#L994) | function/method | <code>validate_review_ledger(ledger: Mapping[str, Any], q201_discovery: Mapping[str, Any], preflight_private_values: Mapping[str, Any], expected_input_hashes: Mapping[str, str], *, expected_source_counts: Mapping[str, int]=EXPECTED_SOURCE_COUNTS, expected_q200_counts: Mapping[str, int]=EXPECTED_Q200_COUNTS, expected_product_other_nonnull: int=EXPECTED_PRODUCT_OTHER_NONNULL, require_initial: bool=False) -&gt; dict[str, Any]</code> | Validate the 33,723 Q201 baseline and 34,565 extended universe. |
| [L1179](../src/april_repro/product_review_ledger.py#L1179) | function/method | <code>build_aggregate_summary(ledger: Mapping[str, Any], counts: Mapping[str, Any], *, ledger_sha256: str) -&gt; dict[str, Any]</code> | Create a strict aggregate-only summary of a validated initial ledger. |
| [L1263](../src/april_repro/product_review_ledger.py#L1263) | function/method | <code>create_initial_review_artifact(root: Path) -&gt; dict[str, Any]</code> | Generate, validate and persist the accepted initial ledger privately. |
| [L1324](../src/april_repro/product_review_ledger.py#L1324) | function/method | <code>validate_review_ledger_file(root: Path, path: Path, *, require_initial: bool=False) -&gt; dict[str, Any]</code> | Validate a private initial or later reviewed ledger without raw output. |

<a id="module-25e95d1b00a7"></a>

## src/april_repro/product_review_ledger_audit.py

[Open source](../src/april_repro/product_review_ledger_audit.py)

Source module docstring:

> Independent offline audit for the private product-semantic review ledger. The auditor intentionally does not import the generator or its validator. It recomputes the typed keys, exact Query-201 membership sequence, all-uncertain initial state, aggregate summary, input hashes, modes, and false guards. Audit output contains no controlled-vocabulary value or per-record hash.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L144](../src/april_repro/product_review_ledger_audit.py#L144) | class | <code>ProductReviewLedgerAuditError(RuntimeError)</code> | A safe audit failure containing no private value. |
| [L148](../src/april_repro/product_review_ledger_audit.py#L148) | class | <code>Checks()</code> |  |
| [L149](../src/april_repro/product_review_ledger_audit.py#L149) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L153](../src/april_repro/product_review_ledger_audit.py#L153) | function/method | <code>Checks.require(self, condition: bool, name: str) -&gt; None</code> |  |
| [L161](../src/april_repro/product_review_ledger_audit.py#L161) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L165](../src/april_repro/product_review_ledger_audit.py#L165) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L173](../src/april_repro/product_review_ledger_audit.py#L173) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L177](../src/april_repro/product_review_ledger_audit.py#L177) | function/method | <code>_valid_timestamp(value: Any) -&gt; bool</code> | Require an ISO-8601 timestamp with an explicit timezone. |
| [L188](../src/april_repro/product_review_ledger_audit.py#L188) | function/method | <code>_git_ignored(root: Path, path: Path) -&gt; bool</code> | Ask Git whether a private artifact path is ignored without echoing it. |
| [L209](../src/april_repro/product_review_ledger_audit.py#L209) | function/method | <code>_read_unique_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L216](../src/april_repro/product_review_ledger_audit.py#L216) | function/method | <code>_read_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L224](../src/april_repro/product_review_ledger_audit.py#L224) | function/method | <code>_read_unique_json.invalid_constant(_: str) -&gt; None</code> |  |
| [L242](../src/april_repro/product_review_ledger_audit.py#L242) | function/method | <code>_hash_parts(parts: Sequence[str]) -&gt; str</code> |  |
| [L253](../src/april_repro/product_review_ledger_audit.py#L253) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L273](../src/april_repro/product_review_ledger_audit.py#L273) | function/method | <code>_json_payload(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L280](../src/april_repro/product_review_ledger_audit.py#L280) | function/method | <code>_input_hashes() -&gt; dict[str, str]</code> |  |
| [L298](../src/april_repro/product_review_ledger_audit.py#L298) | function/method | <code>_typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L336](../src/april_repro/product_review_ledger_audit.py#L336) | function/method | <code>_preflight_product_other(private_values: Mapping[str, Any], checks: Checks, *, expected_nonnull: int, expected_typed_set_sha256: str) -&gt; dict[str, Any]</code> |  |
| [L419](../src/april_repro/product_review_ledger_audit.py#L419) | function/method | <code>_audit_initial_payloads(ledger: Mapping[str, Any], summary: Mapping[str, Any], q201: Mapping[str, Any], preflight_private_values: Mapping[str, Any], ledger_sha256: str, checks: Checks, *, input_hashes: Mapping[str, str], source_counts: Mapping[str, int], q200_counts: Mapping[str, int], product_other_nonnull: int=PRODUCT_OTHER_NONNULL) -&gt; dict[str, Any]</code> | Pure independent recomputation used by the real audit and tests. |
| [L841](../src/april_repro/product_review_ledger_audit.py#L841) | function/method | <code>audit_artifact(directory: Path, root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Audit one generated artifact directory and write a private safe report. |

<a id="module-d0f95cc886b4"></a>

## src/april_repro/profiling.py

[Open source](../src/april_repro/profiling.py)

Source module docstring:

> Auditable, bounded execution of registered, reviewed profiling templates. The registry and SQL code require human/code review: scope labels and the SQL scanner cannot prove that an arbitrary SELECT is free of patient-level output or side-effecting functions. This runner accepts no ad hoc SQL or substitutions.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L25](../src/april_repro/profiling.py#L25) | class | <code>ProfileQuery()</code> |  |
| [L36](../src/april_repro/profiling.py#L36) | function/method | <code>load_queries(root: Path) -&gt; tuple[list[ProfileQuery], str]</code> | Validate and snapshot all templates before opening a DB connection. |
| [L77](../src/april_repro/profiling.py#L77) | function/method | <code>_utc_now() -&gt; str</code> |  |
| [L81](../src/april_repro/profiling.py#L81) | function/method | <code>_write_private(path: Path, data: bytes) -&gt; None</code> |  |
| [L87](../src/april_repro/profiling.py#L87) | function/method | <code>run_profiles(root: Path, selected: list[str] &#124; None=None, timeout_ms: int=10000) -&gt; dict</code> | Return only execution metadata; never include database result rows. |

<a id="module-1ab099914877"></a>

## src/april_repro/query202_adjudication_input.py

[Open source](../src/april_repro/query202_adjudication_input.py)

Source module docstring:

> Compile audited Query-202 A evidence into private adjudication inputs. The compiler is deliberately offline. It accepts only the frozen successful Query-202 pre-adjudication artifact, validates the complete gzip/NDJSON stream, and writes four deterministic private streams. It never prints controlled values and it does not make semantic, route, NDC, product, or event decisions.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L367](../src/april_repro/query202_adjudication_input.py#L367) | class | <code>AdjudicationInputError(RuntimeError)</code> | Fail-closed private input, lineage, schema, or conservation error. |
| [L371](../src/april_repro/query202_adjudication_input.py#L371) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L379](../src/april_repro/query202_adjudication_input.py#L379) | function/method | <code>_file_snapshot(path: Path, label: str, expected_identity: tuple[int, int] &#124; None=None) -&gt; dict[str, Any]</code> |  |
| [L431](../src/april_repro/query202_adjudication_input.py#L431) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L435](../src/april_repro/query202_adjudication_input.py#L435) | function/method | <code>_unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L444](../src/april_repro/query202_adjudication_input.py#L444) | function/method | <code>_reject_json_constant(_: str) -&gt; None</code> |  |
| [L448](../src/april_repro/query202_adjudication_input.py#L448) | function/method | <code>_read_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L472](../src/april_repro/query202_adjudication_input.py#L472) | function/method | <code>_exact_keys(value: Any, expected: set[str], label: str) -&gt; dict[str, Any]</code> |  |
| [L478](../src/april_repro/query202_adjudication_input.py#L478) | function/method | <code>_canonical_json_line(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L485](../src/april_repro/query202_adjudication_input.py#L485) | function/method | <code>_display_path(root: Path, path: Path) -&gt; str</code> |  |
| [L492](../src/april_repro/query202_adjudication_input.py#L492) | function/method | <code>_now() -&gt; str</code> |  |
| [L498](../src/april_repro/query202_adjudication_input.py#L498) | function/method | <code>_validated_time(value: str &#124; None) -&gt; str</code> |  |
| [L511](../src/april_repro/query202_adjudication_input.py#L511) | function/method | <code>_stamp(value: str) -&gt; str</code> |  |
| [L516](../src/april_repro/query202_adjudication_input.py#L516) | class | <code>_PrivateNdjsonReader()</code> | Single-member gzip reader with bounded lines and unique-key JSON. |
| [L519](../src/april_repro/query202_adjudication_input.py#L519) | function/method | <code>_PrivateNdjsonReader.__init__(self, path: Path, expected_identity: tuple[int, int])</code> |  |
| [L530](../src/april_repro/query202_adjudication_input.py#L530) | function/method | <code>_PrivateNdjsonReader.__iter__(self) -&gt; Iterator[dict[str, Any]]</code> |  |
| [L647](../src/april_repro/query202_adjudication_input.py#L647) | class | <code>_RecordCursor()</code> |  |
| [L648](../src/april_repro/query202_adjudication_input.py#L648) | function/method | <code>_RecordCursor.__init__(self, reader: _PrivateNdjsonReader)</code> |  |
| [L652](../src/april_repro/query202_adjudication_input.py#L652) | function/method | <code>_RecordCursor.take(self, record_type: str) -&gt; dict[str, Any]</code> |  |
| [L665](../src/april_repro/query202_adjudication_input.py#L665) | function/method | <code>_RecordCursor.finish(self) -&gt; None</code> |  |
| [L673](../src/april_repro/query202_adjudication_input.py#L673) | class | <code>_GzipNdjsonWriter()</code> | Deterministic single-member gzip writer over one private temporary file. |
| [L676](../src/april_repro/query202_adjudication_input.py#L676) | function/method | <code>_GzipNdjsonWriter.__init__(self, path: Path)</code> |  |
| [L692](../src/april_repro/query202_adjudication_input.py#L692) | function/method | <code>_GzipNdjsonWriter.write(self, value: Mapping[str, Any]) -&gt; None</code> |  |
| [L703](../src/april_repro/query202_adjudication_input.py#L703) | function/method | <code>_GzipNdjsonWriter.finish(self) -&gt; dict[str, Any]</code> |  |
| [L731](../src/april_repro/query202_adjudication_input.py#L731) | function/method | <code>_GzipNdjsonWriter.abort(self) -&gt; None</code> |  |
| [L745](../src/april_repro/query202_adjudication_input.py#L745) | function/method | <code>_write_json_file(path: Path, value: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L786](../src/april_repro/query202_adjudication_input.py#L786) | function/method | <code>_typed_boundary_hash(source_field: str, records: list[dict[str, Any]]) -&gt; str</code> |  |
| [L812](../src/april_repro/query202_adjudication_input.py#L812) | function/method | <code>_semantic_hash(keys: list[tuple[str, str]]) -&gt; str</code> |  |
| [L828](../src/april_repro/query202_adjudication_input.py#L828) | function/method | <code>_route_canonical_hash(values: list[str]) -&gt; str</code> |  |
| [L840](../src/april_repro/query202_adjudication_input.py#L840) | function/method | <code>_encode_tuple(stage: str, kind: str, value: Mapping[str, str &#124; None]) -&gt; bytes</code> |  |
| [L864](../src/april_repro/query202_adjudication_input.py#L864) | function/method | <code>_tuple_hashers(stage_label: str, count: int) -&gt; tuple[Any, Any]</code> |  |
| [L875](../src/april_repro/query202_adjudication_input.py#L875) | function/method | <code>_update_tuple_hashers(hashers: tuple[Any, Any], encoded: bytes, multiplicity: int) -&gt; None</code> |  |
| [L886](../src/april_repro/query202_adjudication_input.py#L886) | function/method | <code>_header(artifact_type: str, created: str, lineage: Mapping[str, Any], component_lineage: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L911](../src/april_repro/query202_adjudication_input.py#L911) | function/method | <code>_privacy() -&gt; dict[str, bool]</code> |  |
| [L921](../src/april_repro/query202_adjudication_input.py#L921) | function/method | <code>_resolve(root: Path, value: Path &#124; str &#124; None, default: Path) -&gt; Path</code> |  |
| [L926](../src/april_repro/query202_adjudication_input.py#L926) | function/method | <code>_configured_project_path(root: Path, value: Path, label: str) -&gt; Path</code> |  |
| [L952](../src/april_repro/query202_adjudication_input.py#L952) | function/method | <code>_load_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |
| [L956](../src/april_repro/query202_adjudication_input.py#L956) | function/method | <code>_component_lineage(root: Path) -&gt; dict[str, Any]</code> |  |
| [L984](../src/april_repro/query202_adjudication_input.py#L984) | function/method | <code>_is_git_ignored(root: Path, path: Path) -&gt; bool</code> |  |
| [L1004](../src/april_repro/query202_adjudication_input.py#L1004) | function/method | <code>_validate_output_parent(root: Path, parent: Path) -&gt; Path</code> |  |
| [L1050](../src/april_repro/query202_adjudication_input.py#L1050) | function/method | <code>_output_parent_identity(path: Path) -&gt; tuple[int, int]</code> |  |
| [L1061](../src/april_repro/query202_adjudication_input.py#L1061) | function/method | <code>_recheck_output_parent(root: Path, parent: Path, expected_identity: tuple[int, int]) -&gt; None</code> |  |
| [L1081](../src/april_repro/query202_adjudication_input.py#L1081) | function/method | <code>_validate_input_lineage(root: Path, directory: Path) -&gt; dict[str, Any]</code> |  |
| [L1247](../src/april_repro/query202_adjudication_input.py#L1247) | function/method | <code>_parse_boundaries(cursor: _RecordCursor) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L1338](../src/april_repro/query202_adjudication_input.py#L1338) | function/method | <code>_route_review_records(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[list[dict[str, Any]], list[dict[str, Any]], str, dict[str, str]]</code> |  |
| [L1436](../src/april_repro/query202_adjudication_input.py#L1436) | function/method | <code>_write_route_review(writer: _GzipNdjsonWriter, created: str, lineage: Mapping[str, Any], component_lineage: Mapping[str, Any], boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Any], dict[str, Any]]</code> |  |
| [L1492](../src/april_repro/query202_adjudication_input.py#L1492) | function/method | <code>_validate_input_header(cursor: _RecordCursor, lineage: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1532](../src/april_repro/query202_adjudication_input.py#L1532) | function/method | <code>_seed_keys(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[list[tuple[str, str]], dict[tuple[str, str], int]]</code> |  |
| [L1555](../src/april_repro/query202_adjudication_input.py#L1555) | function/method | <code>_write_and_validate_semantic_seed(cursor: _RecordCursor, writer: _GzipNdjsonWriter, created: str, lineage: Mapping[str, Any], component_lineage: Mapping[str, Any], boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Any], set[tuple[str, str]]]</code> |  |
| [L1634](../src/april_repro/query202_adjudication_input.py#L1634) | function/method | <code>_typed_boundary_sets(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, set[str &#124; None]]</code> |  |
| [L1646](../src/april_repro/query202_adjudication_input.py#L1646) | function/method | <code>_validate_tuple_bindings(stage: str, kind: str, value: Mapping[str, str &#124; None], semantic_keys: set[tuple[str, str]], boundary_sets: Mapping[str, set[str &#124; None]]) -&gt; None</code> |  |
| [L1691](../src/april_repro/query202_adjudication_input.py#L1691) | function/method | <code>_kind_begin_record(stage: str, kind: str, ndc: bool=False) -&gt; dict[str, Any]</code> |  |
| [L1704](../src/april_repro/query202_adjudication_input.py#L1704) | function/method | <code>_kind_end_record(stage: str, kind: str, records: int, total: int, ndc: bool=False) -&gt; dict[str, Any]</code> |  |
| [L1719](../src/april_repro/query202_adjudication_input.py#L1719) | function/method | <code>_process_crosswalks(cursor: _RecordCursor, local_writer: _GzipNdjsonWriter, ndc_writer: _GzipNdjsonWriter, created: str, lineage: Mapping[str, Any], component_lineage: Mapping[str, Any], semantic_keys: set[tuple[str, str]], boundaries: Mapping[str, Mapping[str, Any]], boundary_sets: Mapping[str, set[str &#124; None]]) -&gt; tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]</code> |  |
| [L1841](../src/april_repro/query202_adjudication_input.py#L1841) | function/method | <code>_process_crosswalks.close_active() -&gt; None</code> |  |
| [L2026](../src/april_repro/query202_adjudication_input.py#L2026) | function/method | <code>_conservation(route_summary: Mapping[str, Any], kind_summaries: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2064](../src/april_repro/query202_adjudication_input.py#L2064) | function/method | <code>_fsync_directory(path: Path) -&gt; None</code> |  |
| [L2072](../src/april_repro/query202_adjudication_input.py#L2072) | function/method | <code>_install_termination_handlers() -&gt; list[tuple[int, Any]]</code> |  |
| [L2075](../src/april_repro/query202_adjudication_input.py#L2075) | function/method | <code>_install_termination_handlers.interrupt(signum: int, _frame: Any) -&gt; None</code> |  |
| [L2096](../src/april_repro/query202_adjudication_input.py#L2096) | function/method | <code>_restore_termination_handlers(installed: list[tuple[int, Any]]) -&gt; None</code> |  |
| [L2104](../src/april_repro/query202_adjudication_input.py#L2104) | function/method | <code>_validate_output_inventory(directory: Path, expected_artifacts: Mapping[str, Mapping[str, Any]], expected_directory_identity: tuple[int, int]) -&gt; None</code> |  |
| [L2152](../src/april_repro/query202_adjudication_input.py#L2152) | function/method | <code>compile_adjudication_input(root: Path, input_directory: Path &#124; str &#124; None=None, output_parent: Path &#124; str &#124; None=None, created_at_utc: str &#124; None=None) -&gt; dict[str, Any]</code> | Compile one immutable, audited Query-202 A artifact into four streams. |

<a id="module-dadd82854641"></a>

## src/april_repro/query202_adjudication_input_audit.py

[Open source](../src/april_repro/query202_adjudication_input_audit.py)

Source module docstring:

> Independent, value-safe audit for the Query-202 adjudication-input handoff. The module deliberately imports neither the adjudication-input compiler nor any Query-202 runner/auditor helper. It reimplements the framing and hashing contracts needed to prove that four private streams are a lossless, review- neutral projection of the frozen Query-202 lifecycle-A artifact. Only aggregate counts and whole-file/set hashes are returned. Exact local values, tuples, NDCs, and per-record hashes never enter errors or the public audit summary.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L703](../src/april_repro/query202_adjudication_input_audit.py#L703) | class | <code>AdjudicationInputAuditError(RuntimeError)</code> | A fixed-name audit failure that never contains a private value. |
| [L707](../src/april_repro/query202_adjudication_input_audit.py#L707) | class | <code>Checks()</code> |  |
| [L708](../src/april_repro/query202_adjudication_input_audit.py#L708) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L713](../src/april_repro/query202_adjudication_input_audit.py#L713) | function/method | <code>Checks.require(self, condition: bool, name: str) -&gt; None</code> |  |
| [L721](../src/april_repro/query202_adjudication_input_audit.py#L721) | function/method | <code>Checks.record_exception(self, name: str) -&gt; None</code> |  |
| [L729](../src/april_repro/query202_adjudication_input_audit.py#L729) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L733](../src/april_repro/query202_adjudication_input_audit.py#L733) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L741](../src/april_repro/query202_adjudication_input_audit.py#L741) | function/method | <code>_safe_relative(value: Any) -&gt; bool</code> |  |
| [L748](../src/april_repro/query202_adjudication_input_audit.py#L748) | function/method | <code>_path_has_symlink(root: Path, path: Path) -&gt; bool</code> |  |
| [L761](../src/april_repro/query202_adjudication_input_audit.py#L761) | function/method | <code>_regular_project_file(root: Path, relative: str) -&gt; Path &#124; None</code> |  |
| [L779](../src/april_repro/query202_adjudication_input_audit.py#L779) | function/method | <code>_regular_project_directory(root: Path, relative: str) -&gt; Path &#124; None</code> |  |
| [L797](../src/april_repro/query202_adjudication_input_audit.py#L797) | function/method | <code>_implementation_bundle_sha256(root: Path, paths: tuple[str, ...]) -&gt; str</code> | Recompute the ordered implementation bundle without shared helpers. |
| [L820](../src/april_repro/query202_adjudication_input_audit.py#L820) | function/method | <code>_load_component_lineage(root: Path, checks: Checks) -&gt; tuple[dict[str, Any], Path]</code> | Independently validate this component's frozen preregistration. |
| [L977](../src/april_repro/query202_adjudication_input_audit.py#L977) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L981](../src/april_repro/query202_adjudication_input_audit.py#L981) | function/method | <code>_parse_utc(value: Any) -&gt; datetime &#124; None</code> |  |
| [L993](../src/april_repro/query202_adjudication_input_audit.py#L993) | function/method | <code>_exact_keys(value: Any, keys: set[str], label: str) -&gt; dict[str, Any]</code> |  |
| [L999](../src/april_repro/query202_adjudication_input_audit.py#L999) | function/method | <code>_strict_equal(left: Any, right: Any) -&gt; bool</code> |  |
| [L1013](../src/april_repro/query202_adjudication_input_audit.py#L1013) | function/method | <code>_exact_int(value: Any, expected: int) -&gt; bool</code> |  |
| [L1017](../src/april_repro/query202_adjudication_input_audit.py#L1017) | function/method | <code>_unique_json(payload: bytes, label: str) -&gt; dict[str, Any]</code> |  |
| [L1018](../src/april_repro/query202_adjudication_input_audit.py#L1018) | function/method | <code>_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1026](../src/april_repro/query202_adjudication_input_audit.py#L1026) | function/method | <code>_unique_json.invalid_constant(_: str) -&gt; None</code> |  |
| [L1044](../src/april_repro/query202_adjudication_input_audit.py#L1044) | function/method | <code>_read_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L1054](../src/april_repro/query202_adjudication_input_audit.py#L1054) | function/method | <code>_git_ignored(root: Path, path: Path) -&gt; bool</code> |  |
| [L1074](../src/april_repro/query202_adjudication_input_audit.py#L1074) | function/method | <code>_file_snapshot(path: Path, label: str) -&gt; dict[str, Any]</code> |  |
| [L1123](../src/april_repro/query202_adjudication_input_audit.py#L1123) | function/method | <code>_recheck_directory_snapshot(directory: Path, expected: Mapping[str, Mapping[str, Any]], label: str, checks: Checks &#124; None, allowed_extra: set[str] &#124; None=None) -&gt; None</code> |  |
| [L1132](../src/april_repro/query202_adjudication_input_audit.py#L1132) | function/method | <code>_recheck_directory_snapshot.require(condition: bool, name: str) -&gt; None</code> |  |
| [L1181](../src/april_repro/query202_adjudication_input_audit.py#L1181) | function/method | <code>_recheck_file_snapshot(path: Path, expected: Mapping[str, Any], label: str, checks: Checks &#124; None) -&gt; None</code> |  |
| [L1189](../src/april_repro/query202_adjudication_input_audit.py#L1189) | function/method | <code>_recheck_file_snapshot.require(condition: bool, name: str) -&gt; None</code> |  |
| [L1200](../src/april_repro/query202_adjudication_input_audit.py#L1200) | function/method | <code>_fsync_directory(path: Path) -&gt; None</code> |  |
| [L1211](../src/april_repro/query202_adjudication_input_audit.py#L1211) | function/method | <code>_write_private_atomic(path: Path, payload: bytes, expected_directory_entries: set[str], publication_guard: Callable[[set[str]], None]) -&gt; dict[str, Any]</code> | Publish one complete private file atomically without overwriting a peer. |
| [L1305](../src/april_repro/query202_adjudication_input_audit.py#L1305) | class | <code>_GzipNdjsonReader()</code> | Bounded single-member gzip+NDJSON reader with duplicate-key checks. |
| [L1311](../src/april_repro/query202_adjudication_input_audit.py#L1311) | function/method | <code>_GzipNdjsonReader.__init__(self, path: Path, label: str)</code> |  |
| [L1325](../src/april_repro/query202_adjudication_input_audit.py#L1325) | function/method | <code>_GzipNdjsonReader.__iter__(self) -&gt; Iterator[dict[str, Any]]</code> |  |
| [L1332](../src/april_repro/query202_adjudication_input_audit.py#L1332) | function/method | <code>_GzipNdjsonReader.__iter__.feed(raw: bytes) -&gt; Iterator[dict[str, Any]]</code> |  |
| [L1417](../src/april_repro/query202_adjudication_input_audit.py#L1417) | class | <code>_Cursor()</code> |  |
| [L1418](../src/april_repro/query202_adjudication_input_audit.py#L1418) | function/method | <code>_Cursor.__init__(self, reader: _GzipNdjsonReader)</code> |  |
| [L1422](../src/april_repro/query202_adjudication_input_audit.py#L1422) | function/method | <code>_Cursor.take(self, record_type: str, label: str) -&gt; dict[str, Any]</code> |  |
| [L1431](../src/april_repro/query202_adjudication_input_audit.py#L1431) | function/method | <code>_Cursor.finish(self, label: str) -&gt; None</code> |  |
| [L1439](../src/april_repro/query202_adjudication_input_audit.py#L1439) | function/method | <code>_semantic_seed_hash(keys: list[tuple[bytes, bytes]]) -&gt; str</code> |  |
| [L1453](../src/april_repro/query202_adjudication_input_audit.py#L1453) | function/method | <code>_typed_boundary_hash(source_field: str, records: list[dict[str, Any]]) -&gt; str</code> |  |
| [L1472](../src/april_repro/query202_adjudication_input_audit.py#L1472) | function/method | <code>_canonical_route_hash(values: list[str]) -&gt; str</code> |  |
| [L1484](../src/april_repro/query202_adjudication_input_audit.py#L1484) | function/method | <code>_encode_tuple(stage: str, kind: str, value: Mapping[str, str &#124; None]) -&gt; bytes</code> |  |
| [L1508](../src/april_repro/query202_adjudication_input_audit.py#L1508) | function/method | <code>_new_tuple_hashers(stage_and_kind: str, count: int) -&gt; tuple[Any, Any]</code> |  |
| [L1519](../src/april_repro/query202_adjudication_input_audit.py#L1519) | function/method | <code>_update_tuple_hashers(hashers: tuple[Any, Any], encoded: bytes, multiplicity: int) -&gt; None</code> |  |
| [L1529](../src/april_repro/query202_adjudication_input_audit.py#L1529) | function/method | <code>_validate_tuple(stage: str, kind: str, value: Any, multiplicity: Any, label: str) -&gt; bytes</code> |  |
| [L1565](../src/april_repro/query202_adjudication_input_audit.py#L1565) | function/method | <code>_validate_tuple_bindings(stage: str, kind: str, value: Mapping[str, str &#124; None], source: Mapping[str, Any], label: str, checks: Checks) -&gt; None</code> |  |
| [L1612](../src/april_repro/query202_adjudication_input_audit.py#L1612) | function/method | <code>_expected_input_lineage() -&gt; dict[str, Any]</code> |  |
| [L1626](../src/april_repro/query202_adjudication_input_audit.py#L1626) | function/method | <code>_validate_header(cursor: _Cursor, stream_name: str, created_at_utc: str, component_lineage: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L1679](../src/april_repro/query202_adjudication_input_audit.py#L1679) | function/method | <code>_load_source_documents(root: Path, checks: Checks) -&gt; tuple[dict[str, Any], dict[str, Any], dict[str, Any], Path, dict[str, dict[str, Any]], dict[str, Any]]</code> |  |
| [L1865](../src/april_repro/query202_adjudication_input_audit.py#L1865) | function/method | <code>_stream_source_private(path: Path, summary: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> | Read the pinned A stream and recover exact review universes. |
| [L2178](../src/april_repro/query202_adjudication_input_audit.py#L2178) | function/method | <code>_stream_result(reader: _GzipNdjsonReader) -&gt; dict[str, Any]</code> |  |
| [L2189](../src/april_repro/query202_adjudication_input_audit.py#L2189) | function/method | <code>_finish_stream(cursor: _Cursor, reader: _GzipNdjsonReader, stream_name: str, section_counts: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L2217](../src/april_repro/query202_adjudication_input_audit.py#L2217) | function/method | <code>_audit_semantic_stream(path: Path, source: Mapping[str, Any], created_at_utc: str, component_lineage: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L2311](../src/april_repro/query202_adjudication_input_audit.py#L2311) | function/method | <code>_audit_route_stream(path: Path, source: Mapping[str, Any], created_at_utc: str, component_lineage: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L2506](../src/april_repro/query202_adjudication_input_audit.py#L2506) | function/method | <code>_audit_local_stream(path: Path, source: Mapping[str, Any], created_at_utc: str, component_lineage: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L2628](../src/april_repro/query202_adjudication_input_audit.py#L2628) | function/method | <code>_audit_ndc_stream(path: Path, source: Mapping[str, Any], created_at_utc: str, component_lineage: Mapping[str, Any], checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L2837](../src/april_repro/query202_adjudication_input_audit.py#L2837) | function/method | <code>_check_public_keys(value: Any, checks: Checks, label: str) -&gt; None</code> |  |
| [L2850](../src/april_repro/query202_adjudication_input_audit.py#L2850) | function/method | <code>_expected_conservation(source: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2874](../src/april_repro/query202_adjudication_input_audit.py#L2874) | function/method | <code>_standard_stream_result(stream_name: str, result: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2888](../src/april_repro/query202_adjudication_input_audit.py#L2888) | function/method | <code>_validate_stream_metadata(value: Any, expected: Mapping[str, Any], label: str, checks: Checks) -&gt; None</code> |  |
| [L2921](../src/april_repro/query202_adjudication_input_audit.py#L2921) | function/method | <code>_load_target_documents(root: Path, directory: Path, checks: Checks) -&gt; tuple[dict[str, Any], bytes, dict[str, Any], bytes]</code> |  |
| [L2956](../src/april_repro/query202_adjudication_input_audit.py#L2956) | function/method | <code>_audit_complete_artifact(root: Path, directory: Path, checks: Checks) -&gt; tuple[dict[str, Any], dict[str, Any]]</code> |  |
| [L3255](../src/april_repro/query202_adjudication_input_audit.py#L3255) | function/method | <code>_publication_guard(root: Path, contract: Mapping[str, Any], allowed_target_entries: set[str]) -&gt; None</code> |  |
| [L3313](../src/april_repro/query202_adjudication_input_audit.py#L3313) | function/method | <code>audit_query202_adjudication_input(root: Path, artifact_directory: Path) -&gt; dict[str, Any]</code> | Audit one compiled handoff offline and persist a value-safe result. |

<a id="module-64eb239fa72d"></a>

## src/april_repro/query202_adjudication_input_preregistration.py

[Open source](../src/april_repro/query202_adjudication_input_preregistration.py)

Source module docstring:

> Freeze validation for the offline Query-202 adjudication-input compiler.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L383](../src/april_repro/query202_adjudication_input_preregistration.py#L383) | function/method | <code>_sha256(path: Path) -&gt; str</code> |  |
| [L391](../src/april_repro/query202_adjudication_input_preregistration.py#L391) | function/method | <code>implementation_bundle_sha256(root: Path, paths: Sequence[str]) -&gt; str</code> |  |
| [L408](../src/april_repro/query202_adjudication_input_preregistration.py#L408) | function/method | <code>_parse_query202_adjudication_input_preregistration(payload: bytes) -&gt; dict[str, Any]</code> |  |
| [L414](../src/april_repro/query202_adjudication_input_preregistration.py#L414) | function/method | <code>_read_query202_adjudication_input_preregistration_snapshot(root: Path) -&gt; tuple[dict[str, Any], str]</code> |  |
| [L425](../src/april_repro/query202_adjudication_input_preregistration.py#L425) | function/method | <code>read_query202_adjudication_input_preregistration(root: Path) -&gt; dict[str, Any]</code> |  |
| [L432](../src/april_repro/query202_adjudication_input_preregistration.py#L432) | function/method | <code>_safe_relative(value: object) -&gt; bool</code> |  |
| [L439](../src/april_repro/query202_adjudication_input_preregistration.py#L439) | function/method | <code>_project_regular_file(root: Path, relative: object) -&gt; Path &#124; None</code> |  |
| [L458](../src/april_repro/query202_adjudication_input_preregistration.py#L458) | function/method | <code>_strict_value_equal(actual: object, expected: object) -&gt; bool</code> | Compare TOML contract values without bool/int type coercion. |
| [L481](../src/april_repro/query202_adjudication_input_preregistration.py#L481) | function/method | <code>_validate_exact_keys(actual: Mapping[str, Any], expected_keys: Sequence[str] &#124; frozenset[str], label: str, errors: list[str]) -&gt; None</code> |  |
| [L498](../src/april_repro/query202_adjudication_input_preregistration.py#L498) | function/method | <code>_validate_exact_mapping(actual: object, expected: Mapping[str, Any], label: str, errors: list[str]) -&gt; None</code> |  |
| [L513](../src/april_repro/query202_adjudication_input_preregistration.py#L513) | function/method | <code>validate_query202_adjudication_input_preregistration(config: Mapping[str, Any]) -&gt; list[str]</code> |  |
| [L628](../src/april_repro/query202_adjudication_input_preregistration.py#L628) | function/method | <code>query202_adjudication_input_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |

<a id="module-6305b8e29b5a"></a>

## src/april_repro/query202_contract.py

[Open source](../src/april_repro/query202_contract.py)

Source module docstring:

> Pure controls for the proposed D005 Query 202 extraction architecture. This module does not connect to MIMIC, classify route values, or construct a cohort. It makes two execution controls testable before any database run: the stable 64-way subject partition and the mutually exclusive event-to-order link status. The matching SQL contract is recorded in the Query 202 preregistration; changing either reducer requires a new component version.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L58](../src/april_repro/query202_contract.py#L58) | function/method | <code>query202_subject_bucket(subject_id: int &#124; None) -&gt; int</code> | Assign one subject to the preregistered 64-way Query 202 bucket. |
| [L75](../src/april_repro/query202_contract.py#L75) | function/method | <code>validate_query202_bucket_indices(indices: list[int] &#124; tuple[int, ...]) -&gt; None</code> | Reject an incomplete, duplicated, reordered, or non-integer plan. |
| [L81](../src/april_repro/query202_contract.py#L81) | function/method | <code>reduce_primary_link_status(flags: Mapping[str, bool], *, compatible_prescription_component_count: int) -&gt; str</code> | Reduce overlapping diagnostics to one preregistered primary status. |
| [L122](../src/april_repro/query202_contract.py#L122) | function/method | <code>identity_chain_status(primary_link_status: str) -&gt; str</code> | Collapse the primary partition to the mapping reducer's three states. |

<a id="module-e35adadd0639"></a>

## src/april_repro/query202_human_adjudication.py

[Open source](../src/april_repro/query202_human_adjudication.py)

Source module docstring:

> Create and validate the private Query-202 human-adjudication workspace. The workspace is an offline, exact-value handoff. It separates immutable source views from append-only human decision ledgers. Initialization assigns stable review identifiers and writes only &#96;&#96;unreviewed&#96;&#96;/&#96;&#96;uncertain&#96;&#96; or &#96;&#96;unreviewed&#96;&#96;/&#96;&#96;unknown&#96;&#96; decisions; it never classifies a medication or route. All returned reports are aggregate-only. This module deliberately does not import the upstream compiler. The frozen gzip streams are validated from their own bytes and from the hashes and cardinalities in the component configuration.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L391](../src/april_repro/query202_human_adjudication.py#L391) | class | <code>HumanAdjudicationError(RuntimeError)</code> | Fail-closed lineage, privacy, schema, or conservation error. |
| [L395](../src/april_repro/query202_human_adjudication.py#L395) | function/method | <code>_formal_preregistration_report(root: Path) -&gt; Mapping[str, Any]</code> | Load the independently implemented formal-readiness report. |
| [L409](../src/april_repro/query202_human_adjudication.py#L409) | function/method | <code>_require_formal_preregistration_ready(root: Path, contract: Mapping[str, Any]) -&gt; None</code> | Require the exact frozen preregistration gate for formal workspaces. |
| [L454](../src/april_repro/query202_human_adjudication.py#L454) | function/method | <code>_unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L463](../src/april_repro/query202_human_adjudication.py#L463) | function/method | <code>_reject_constant(_: str) -&gt; None</code> |  |
| [L467](../src/april_repro/query202_human_adjudication.py#L467) | function/method | <code>_json_loads(raw: bytes, label: str) -&gt; Any</code> |  |
| [L480](../src/april_repro/query202_human_adjudication.py#L480) | function/method | <code>_canonical_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L490](../src/april_repro/query202_human_adjudication.py#L490) | function/method | <code>_json_line(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L494](../src/april_repro/query202_human_adjudication.py#L494) | function/method | <code>_pretty_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L507](../src/april_repro/query202_human_adjudication.py#L507) | function/method | <code>_record_sha(record: Mapping[str, Any]) -&gt; str</code> |  |
| [L511](../src/april_repro/query202_human_adjudication.py#L511) | function/method | <code>_absolute_parts(path: Path) -&gt; tuple[str, ...]</code> |  |
| [L518](../src/april_repro/query202_human_adjudication.py#L518) | function/method | <code>_open_directory_fd(path: Path) -&gt; tuple[int, tuple[tuple[int, int], ...]]</code> | Open every directory component without following symlinks. |
| [L559](../src/april_repro/query202_human_adjudication.py#L559) | function/method | <code>_open_parent_fd(path: Path) -&gt; tuple[int, str, tuple[tuple[int, int], ...]]</code> |  |
| [L567](../src/april_repro/query202_human_adjudication.py#L567) | function/method | <code>_lstat_nofollow(path: Path) -&gt; tuple[os.stat_result, tuple[tuple[int, int], ...]]</code> |  |
| [L586](../src/april_repro/query202_human_adjudication.py#L586) | function/method | <code>_ensure_private_directory(root: Path, relative: Path) -&gt; tuple[int, tuple[tuple[int, int], ...]]</code> | Create/open a root-relative directory through one anchored fd chain. |
| [L621](../src/april_repro/query202_human_adjudication.py#L621) | function/method | <code>_remove_tree_at(parent_descriptor: int, name: str) -&gt; None</code> | Remove one controlled temporary tree without reopening its parents. |
| [L639](../src/april_repro/query202_human_adjudication.py#L639) | function/method | <code>_remove_tree_if_identity_at(parent_descriptor: int, name: str, expected_identity: tuple[int, int]) -&gt; None</code> | Remove a controlled workspace tree without deleting a raced-in leaf. |
| [L654](../src/april_repro/query202_human_adjudication.py#L654) | function/method | <code>_open_relative_parent_at(root_descriptor: int, relative: str, label: str) -&gt; tuple[int, str]</code> | Open an existing parent strictly beneath one already-open directory. |
| [L700](../src/april_repro/query202_human_adjudication.py#L700) | function/method | <code>_unlink_file_if_identity_at(parent_descriptor: int, name: str, expected_identity: tuple[int, int]) -&gt; None</code> | Remove only the still-named regular file created by this process. |
| [L718](../src/april_repro/query202_human_adjudication.py#L718) | function/method | <code>_mkdir_private_at(root_descriptor: int, relative: str) -&gt; tuple[int, int]</code> | Create one 0700 directory through the held temporary-workspace fd. |
| [L768](../src/april_repro/query202_human_adjudication.py#L768) | function/method | <code>_clear_controlled_directory_fd(descriptor: int) -&gt; None</code> | Scrub the contents of the held controlled directory after failure. |
| [L825](../src/april_repro/query202_human_adjudication.py#L825) | function/method | <code>_scrub_and_remove_controlled_directory_at(parent_descriptor: int, controlled_descriptor: int, expected_identity: tuple[int, int]) -&gt; None</code> | Scrub the held tree and remove any same-parent name still binding it. |
| [L856](../src/april_repro/query202_human_adjudication.py#L856) | function/method | <code>_rename_directory_noreplace(source_parent_descriptor: int, source_name: str, destination_parent_descriptor: int, destination_name: str) -&gt; None</code> | Atomically publish a directory without replacing an existing leaf. |
| [L905](../src/april_repro/query202_human_adjudication.py#L905) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L910](../src/april_repro/query202_human_adjudication.py#L910) | function/method | <code>_safe_relative(value: object, label: str) -&gt; Path</code> |  |
| [L919](../src/april_repro/query202_human_adjudication.py#L919) | function/method | <code>_project_path(root: Path, value: object, label: str, *, must_exist: bool=True) -&gt; Path</code> |  |
| [L943](../src/april_repro/query202_human_adjudication.py#L943) | function/method | <code>_same_open_snapshot(left: os.stat_result, right: os.stat_result) -&gt; bool</code> |  |
| [L956](../src/april_repro/query202_human_adjudication.py#L956) | function/method | <code>_snapshot_file(path: Path, label: str, *, retain_payload: bool=False) -&gt; dict[str, Any]</code> |  |
| [L1018](../src/april_repro/query202_human_adjudication.py#L1018) | function/method | <code>_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L1032](../src/april_repro/query202_human_adjudication.py#L1032) | function/method | <code>_snapshot_directory(path: Path, label: str) -&gt; dict[str, Any]</code> |  |
| [L1067](../src/april_repro/query202_human_adjudication.py#L1067) | function/method | <code>_directory_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L1076](../src/april_repro/query202_human_adjudication.py#L1076) | function/method | <code>_require_hash(snapshot: Mapping[str, Any], expected: object, label: str) -&gt; None</code> |  |
| [L1083](../src/april_repro/query202_human_adjudication.py#L1083) | function/method | <code>_require_positive_int(value: object, label: str, *, allow_zero: bool=False) -&gt; int</code> |  |
| [L1090](../src/april_repro/query202_human_adjudication.py#L1090) | function/method | <code>_exact_keys(value: object, keys: Iterable[str], label: str) -&gt; Mapping[str, Any]</code> |  |
| [L1097](../src/april_repro/query202_human_adjudication.py#L1097) | function/method | <code>_strict_utc(value: object) -&gt; bool</code> |  |
| [L1107](../src/april_repro/query202_human_adjudication.py#L1107) | function/method | <code>_now_utc() -&gt; str</code> |  |
| [L1111](../src/april_repro/query202_human_adjudication.py#L1111) | function/method | <code>_timestamp_directory(value: str) -&gt; str</code> |  |
| [L1118](../src/april_repro/query202_human_adjudication.py#L1118) | function/method | <code>_write_private_at(root_descriptor: int, relative: str, payload: bytes) -&gt; dict[str, Any]</code> | Create and durably verify one private file beneath an anchored fd. |
| [L1194](../src/april_repro/query202_human_adjudication.py#L1194) | function/method | <code>_write_ndjson_at(root_descriptor: int, relative: str, records: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1206](../src/april_repro/query202_human_adjudication.py#L1206) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; dict[str, Any]</code> |  |
| [L1258](../src/april_repro/query202_human_adjudication.py#L1258) | function/method | <code>_write_ndjson(path: Path, records: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1262](../src/april_repro/query202_human_adjudication.py#L1262) | function/method | <code>_read_ndjson_payload(raw: bytes, label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L1276](../src/april_repro/query202_human_adjudication.py#L1276) | function/method | <code>_read_ndjson_snapshot(snapshot: Mapping[str, Any], label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L1283](../src/april_repro/query202_human_adjudication.py#L1283) | function/method | <code>_decompress_one_gzip(stored: bytes, label: str) -&gt; bytes</code> |  |
| [L1294](../src/april_repro/query202_human_adjudication.py#L1294) | function/method | <code>_bundle(root: Path, paths: Sequence[str]) -&gt; dict[str, Any]</code> |  |
| [L1323](../src/april_repro/query202_human_adjudication.py#L1323) | function/method | <code>_git_ignored(root: Path, path: Path) -&gt; bool</code> |  |
| [L1338](../src/april_repro/query202_human_adjudication.py#L1338) | function/method | <code>_local_index_contract(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1422](../src/april_repro/query202_human_adjudication.py#L1422) | function/method | <code>_load_contract(root: Path, config_path: Path, *, allow_proposed: bool) -&gt; dict[str, Any]</code> |  |
| [L1673](../src/april_repro/query202_human_adjudication.py#L1673) | function/method | <code>_validate_public_json(snapshot: Mapping[str, Any], label: str) -&gt; Mapping[str, Any]</code> |  |
| [L1683](../src/april_repro/query202_human_adjudication.py#L1683) | function/method | <code>_artifact_file(directory: Path, value: object, label: str) -&gt; Path</code> |  |
| [L1689](../src/april_repro/query202_human_adjudication.py#L1689) | function/method | <code>_source_inventory(root: Path, contract: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1828](../src/april_repro/query202_human_adjudication.py#L1828) | function/method | <code>_finish_source_closure(source_inventory: Mapping[str, Any], contract: Mapping[str, Any]) -&gt; None</code> |  |
| [L1849](../src/april_repro/query202_human_adjudication.py#L1849) | function/method | <code>_stream_records(snapshot: Mapping[str, Any], section: Mapping[str, Any], label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L1867](../src/april_repro/query202_human_adjudication.py#L1867) | function/method | <code>_semantic_set_hash(items: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L1883](../src/april_repro/query202_human_adjudication.py#L1883) | function/method | <code>_route_set_hash(items: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L1895](../src/april_repro/query202_human_adjudication.py#L1895) | function/method | <code>_parse_semantic_template(records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]) -&gt; list[dict[str, Any]]</code> |  |
| [L1962](../src/april_repro/query202_human_adjudication.py#L1962) | function/method | <code>_parse_route_template(records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]) -&gt; tuple[list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L2111](../src/april_repro/query202_human_adjudication.py#L2111) | function/method | <code>_build_local_evidence_index(destination_descriptor: int, destination_relative: str, source_inventory: Mapping[str, Any], config: Mapping[str, Any], semantic_items: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> | Scan the frozen local stream once and write the immutable bridge index. |
| [L2140](../src/april_repro/query202_human_adjudication.py#L2140) | function/method | <code>_build_local_evidence_index.handle_record(record: Mapping[str, Any]) -&gt; None</code> |  |
| [L2254](../src/april_repro/query202_human_adjudication.py#L2254) | function/method | <code>_build_local_evidence_index.consume(raw: bytes) -&gt; None</code> |  |
| [L2377](../src/april_repro/query202_human_adjudication.py#L2377) | function/method | <code>_semantic_default_revision(review_id: str, semantic_config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2407](../src/april_repro/query202_human_adjudication.py#L2407) | function/method | <code>_route_default_revision(review_id: str) -&gt; dict[str, Any]</code> |  |
| [L2424](../src/april_repro/query202_human_adjudication.py#L2424) | function/method | <code>_source_batch_records(kind: str, batch_index: int, batch_count: int, items: Sequence[Mapping[str, Any]], memberships: Sequence[Mapping[str, Any]]=()) -&gt; list[Mapping[str, Any]]</code> |  |
| [L2452](../src/april_repro/query202_human_adjudication.py#L2452) | function/method | <code>_decision_batch_records(kind: str, batch_index: int, batch_count: int, source_relative: str, source_meta: Mapping[str, Any], items: Sequence[Mapping[str, Any]], config_sha256: str, semantic_config: Mapping[str, Any] &#124; None=None) -&gt; list[Mapping[str, Any]]</code> |  |
| [L2483](../src/april_repro/query202_human_adjudication.py#L2483) | function/method | <code>_manifest_relative(root: Path, path: Path) -&gt; str</code> |  |
| [L2490](../src/april_repro/query202_human_adjudication.py#L2490) | function/method | <code>_initial_workspace_guards(*, proposed: bool) -&gt; dict[str, bool]</code> |  |
| [L2515](../src/april_repro/query202_human_adjudication.py#L2515) | function/method | <code>_initial_manifest(root: Path, destination: Path, created_at: str, contract: Mapping[str, Any], source_inventory: Mapping[str, Any], immutable_files: Sequence[Mapping[str, Any]], editable_files: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L2588](../src/april_repro/query202_human_adjudication.py#L2588) | function/method | <code>initialize_human_adjudication_workspace(root: Path, config_path: Path=CONFIG_PATH, output_parent: Path &#124; None=None, *, created_at_utc: str &#124; None=None, allow_proposed: bool=False) -&gt; dict[str, Any]</code> | Initialize a private all-unreviewed workspace atomically. |
| [L2999](../src/april_repro/query202_human_adjudication.py#L2999) | function/method | <code>_nonempty_text(value: object, label: str, maximum: int=MAX_TEXT_BYTES) -&gt; str</code> |  |
| [L3005](../src/april_repro/query202_human_adjudication.py#L3005) | function/method | <code>_evidence_refs(value: object, label: str, evidence_registry: Mapping[str, Mapping[str, Any]], *, required: bool, review_id: str &#124; None=None) -&gt; list[str]</code> |  |
| [L3038](../src/april_repro/query202_human_adjudication.py#L3038) | function/method | <code>_validate_revision_common(record: Mapping[str, Any], expected_type: str, id_pattern: re.Pattern[str]) -&gt; tuple[str, int, str &#124; None, str]</code> |  |
| [L3058](../src/april_repro/query202_human_adjudication.py#L3058) | function/method | <code>_validate_semantic_revision(record: Mapping[str, Any], semantic_config: Mapping[str, Any], evidence_registry: Mapping[str, Mapping[str, Any]], *, bind_source_template_to_item: bool=True) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L3138](../src/april_repro/query202_human_adjudication.py#L3138) | function/method | <code>_validate_route_revision(record: Mapping[str, Any], evidence_registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L3180](../src/april_repro/query202_human_adjudication.py#L3180) | function/method | <code>_active_batch_hash(kind: str, batch_index: int, active: Mapping[str, Mapping[str, Any]]) -&gt; str</code> |  |
| [L3195](../src/april_repro/query202_human_adjudication.py#L3195) | function/method | <code>_validate_attestation_ledger(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], batch_bindings: Mapping[tuple[str, int], Mapping[str, Any]], group_registry_sha256: str) -&gt; tuple[set[tuple[str, int]], set[str], dict[str, Mapping[str, Any]], dict[tuple[str, int], str]]</code> |  |
| [L3296](../src/april_repro/query202_human_adjudication.py#L3296) | function/method | <code>_validate_source_batch(records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int, expected_items: Sequence[Mapping[str, Any]], expected_memberships: Sequence[Mapping[str, Any]]) -&gt; None</code> |  |
| [L3318](../src/april_repro/query202_human_adjudication.py#L3318) | function/method | <code>_validate_decision_ledger(records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int, source_relative: str, source_snapshot: Mapping[str, Any], expected_ids: Sequence[str], contract: Mapping[str, Any], evidence_registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], bool, int, str, set[str], dict[tuple[str, str, int], Mapping[str, Any]]]</code> |  |
| [L3429](../src/april_repro/query202_human_adjudication.py#L3429) | function/method | <code>_validate_group_revision(record: Mapping[str, Any], all_ids: set[str], semantic_config: Mapping[str, Any], group_config: Mapping[str, Any], evidence_registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L3525](../src/april_repro/query202_human_adjudication.py#L3525) | function/method | <code>_validate_group_ledger(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], all_ids: set[str], semantic_active: Mapping[str, Mapping[str, Any]], evidence_registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], set[str], dict[tuple[str, str, int], Mapping[str, Any]]]</code> |  |
| [L3614](../src/april_repro/query202_human_adjudication.py#L3614) | function/method | <code>_workspace_paths(workspace: Path, semantic_batches: int) -&gt; dict[str, list[tuple[str, Path]]]</code> |  |
| [L3638](../src/april_repro/query202_human_adjudication.py#L3638) | function/method | <code>_expected_workspace_entries(paths: Mapping[str, Sequence[tuple[str, Path]]]) -&gt; set[str]</code> |  |
| [L3642](../src/april_repro/query202_human_adjudication.py#L3642) | function/method | <code>_revision_event_subject(binding: Mapping[str, Any]) -&gt; str</code> |  |
| [L3652](../src/april_repro/query202_human_adjudication.py#L3652) | function/method | <code>_attestation_event_subject(binding: Mapping[str, Any]) -&gt; str</code> |  |
| [L3656](../src/april_repro/query202_human_adjudication.py#L3656) | function/method | <code>_utc_datetime(value: str) -&gt; datetime</code> |  |
| [L3660](../src/april_repro/query202_human_adjudication.py#L3660) | function/method | <code>_validate_revision_event_ledger(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], expected_revisions: Mapping[tuple[str, str, int], Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], set[str]]</code> |  |
| [L3754](../src/april_repro/query202_human_adjudication.py#L3754) | function/method | <code>_active_workspace_state_hash(batch_bindings: Mapping[tuple[str, int], Mapping[str, Any]], groups: Mapping[str, Mapping[str, Any]], current_attestations: Mapping[tuple[str, int], str]) -&gt; str</code> |  |
| [L3793](../src/april_repro/query202_human_adjudication.py#L3793) | function/method | <code>_validate_workspace_event_ledger(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], manifest: Mapping[str, Any], revision_events: Mapping[str, Mapping[str, Any]], attestations: Mapping[str, Mapping[str, Any]], *, data_complete: bool, active_state_sha256: str, single_reviewer_id: str &#124; None) -&gt; dict[str, Any]</code> |  |
| [L3969](../src/april_repro/query202_human_adjudication.py#L3969) | function/method | <code>_validate_evidence_registry(snapshot: Mapping[str, Any], contract: Mapping[str, Any], workspace: Path, all_review_ids: set[str], file_snapshots: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], set[str]]</code> |  |
| [L4108](../src/april_repro/query202_human_adjudication.py#L4108) | function/method | <code>_resolve_local_tuple_evidence(index_snapshot: Mapping[str, Any], config: Mapping[str, Any], evidence_registry: dict[str, Mapping[str, Any]], semantic_items: Sequence[Mapping[str, Any]]) -&gt; None</code> | Resolve local locators from the immutable private ordinal index. |
| [L4172](../src/april_repro/query202_human_adjudication.py#L4172) | function/method | <code>_walk_workspace_files(workspace: Path) -&gt; tuple[set[str], list[Path]]</code> |  |
| [L4176](../src/april_repro/query202_human_adjudication.py#L4176) | function/method | <code>_walk_workspace_files.visit(descriptor: int, relative: Path) -&gt; None</code> |  |
| [L4244](../src/april_repro/query202_human_adjudication.py#L4244) | function/method | <code>validate_human_adjudication_workspace(root: Path, workspace_directory: Path, config_path: Path=CONFIG_PATH, *, allow_proposed: bool=False, _logical_workspace_directory: Path &#124; None=None) -&gt; dict[str, Any]</code> | Validate source conservation, immutable views, ledgers, and closure. |

<a id="module-0c6d2b46e023"></a>

## src/april_repro/query202_human_adjudication_audit.py

[Open source](../src/april_repro/query202_human_adjudication_audit.py)

Source module docstring:

> Independent structural audit of a formal Query-202 review workspace. This module intentionally does not import the workspace generator or validator. It re-parses the frozen source streams and the private workspace with its own schema, hashing, revision-chain, evidence-resolution, and snapshot-closure logic. The resulting report is aggregate-only. The workspace entry point has deliberately narrow scope: it audits a workspace after human review, does not establish clinical correctness, and cannot make the workspace eligible for the later separate freeze. A separate entry point independently audits the compiled artifact and writes the only audit eligible for the freeze operation.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L433](../src/april_repro/query202_human_adjudication_audit.py#L433) | class | <code>HumanAdjudicationAuditError(RuntimeError)</code> | Fail-closed structural-audit error with no private value content. |
| [L437](../src/april_repro/query202_human_adjudication_audit.py#L437) | function/method | <code>_unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L446](../src/april_repro/query202_human_adjudication_audit.py#L446) | function/method | <code>_reject_constant(_: str) -&gt; None</code> |  |
| [L450](../src/april_repro/query202_human_adjudication_audit.py#L450) | function/method | <code>_json_loads(raw: bytes, label: str) -&gt; Any</code> |  |
| [L465](../src/april_repro/query202_human_adjudication_audit.py#L465) | function/method | <code>_canonical_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L475](../src/april_repro/query202_human_adjudication_audit.py#L475) | function/method | <code>_record_sha(record: Mapping[str, Any]) -&gt; str</code> |  |
| [L479](../src/april_repro/query202_human_adjudication_audit.py#L479) | function/method | <code>_pretty_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L497](../src/april_repro/query202_human_adjudication_audit.py#L497) | function/method | <code>_sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L510](../src/april_repro/query202_human_adjudication_audit.py#L510) | function/method | <code>_audit_time(value: str &#124; None) -&gt; str</code> |  |
| [L519](../src/april_repro/query202_human_adjudication_audit.py#L519) | function/method | <code>_exact_keys(value: object, keys: Iterable[str], label: str) -&gt; Mapping[str, Any]</code> |  |
| [L526](../src/april_repro/query202_human_adjudication_audit.py#L526) | function/method | <code>_positive_int(value: object, label: str, *, allow_zero: bool=False) -&gt; int</code> |  |
| [L533](../src/april_repro/query202_human_adjudication_audit.py#L533) | function/method | <code>_nonempty_text(value: object, label: str, maximum: int=MAX_TEXT_BYTES) -&gt; str</code> |  |
| [L543](../src/april_repro/query202_human_adjudication_audit.py#L543) | function/method | <code>_strict_utc(value: object) -&gt; bool</code> |  |
| [L553](../src/april_repro/query202_human_adjudication_audit.py#L553) | function/method | <code>_valid_strict_timestamp_leaf(value: object) -&gt; bool</code> |  |
| [L563](../src/april_repro/query202_human_adjudication_audit.py#L563) | function/method | <code>_safe_relative(value: object, label: str) -&gt; Path</code> |  |
| [L572](../src/april_repro/query202_human_adjudication_audit.py#L572) | function/method | <code>_project_path(root: Path, value: object, label: str) -&gt; Path</code> |  |
| [L587](../src/april_repro/query202_human_adjudication_audit.py#L587) | function/method | <code>_open_beneath(root: Path, path: Path, label: str) -&gt; tuple[int, os.stat_result, tuple[tuple[int, int, int], ...]]</code> | Open &#96;&#96;path&#96;&#96; through root-anchored, no-follow directory descriptors. |
| [L653](../src/april_repro/query202_human_adjudication_audit.py#L653) | function/method | <code>_same_stat(left: os.stat_result, right: os.stat_result) -&gt; bool</code> |  |
| [L666](../src/april_repro/query202_human_adjudication_audit.py#L666) | function/method | <code>_snapshot_file(path: Path, label: str, *, retain_payload: bool=False, root: Path &#124; None=None, maximum_bytes: int &#124; None=None) -&gt; dict[str, Any]</code> |  |
| [L757](../src/april_repro/query202_human_adjudication_audit.py#L757) | function/method | <code>_snapshot_directory(path: Path, label: str, *, root: Path &#124; None=None) -&gt; dict[str, Any]</code> |  |
| [L800](../src/april_repro/query202_human_adjudication_audit.py#L800) | function/method | <code>_file_seal(value: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L816](../src/april_repro/query202_human_adjudication_audit.py#L816) | function/method | <code>_directory_seal(value: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L830](../src/april_repro/query202_human_adjudication_audit.py#L830) | function/method | <code>_require_hash(snapshot: Mapping[str, Any], expected: object, label: str) -&gt; None</code> |  |
| [L837](../src/april_repro/query202_human_adjudication_audit.py#L837) | function/method | <code>_read_json(snapshot: Mapping[str, Any], label: str) -&gt; Mapping[str, Any]</code> |  |
| [L847](../src/april_repro/query202_human_adjudication_audit.py#L847) | function/method | <code>_read_ndjson(raw: bytes, label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L861](../src/april_repro/query202_human_adjudication_audit.py#L861) | function/method | <code>_snapshot_records(snapshot: Mapping[str, Any], label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L870](../src/april_repro/query202_human_adjudication_audit.py#L870) | function/method | <code>_one_gzip(stored: bytes, label: str) -&gt; bytes</code> |  |
| [L881](../src/april_repro/query202_human_adjudication_audit.py#L881) | function/method | <code>_stream_records(snapshot: Mapping[str, Any], section: Mapping[str, Any], label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L898](../src/april_repro/query202_human_adjudication_audit.py#L898) | function/method | <code>_bundle(root: Path, paths: Sequence[str], label: str) -&gt; dict[str, Any]</code> |  |
| [L916](../src/april_repro/query202_human_adjudication_audit.py#L916) | function/method | <code>_git_ignored(root: Path, path: Path) -&gt; bool</code> |  |
| [L931](../src/april_repro/query202_human_adjudication_audit.py#L931) | function/method | <code>_local_index_contract(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1016](../src/april_repro/query202_human_adjudication_audit.py#L1016) | function/method | <code>_contract_projection(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1044](../src/april_repro/query202_human_adjudication_audit.py#L1044) | function/method | <code>_scientific_contract_sha256(config: Mapping[str, Any]) -&gt; str</code> |  |
| [L1054](../src/april_repro/query202_human_adjudication_audit.py#L1054) | function/method | <code>_execution_snapshot_summary(config: Mapping[str, Any], snapshots: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, object]</code> |  |
| [L1086](../src/april_repro/query202_human_adjudication_audit.py#L1086) | function/method | <code>_python_runtime_snapshot(root: Path) -&gt; tuple[dict[str, object], dict[str, Any], Path]</code> |  |
| [L1115](../src/april_repro/query202_human_adjudication_audit.py#L1115) | function/method | <code>_snapshot_runtime_locator(root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Snapshot the locked interpreter locator separately from its target. |
| [L1185](../src/april_repro/query202_human_adjudication_audit.py#L1185) | function/method | <code>_runtime_locator_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L1202](../src/april_repro/query202_human_adjudication_audit.py#L1202) | function/method | <code>_python_runtime_summary(root: Path) -&gt; dict[str, object]</code> |  |
| [L1207](../src/april_repro/query202_human_adjudication_audit.py#L1207) | function/method | <code>_verify_test_attestation(root: Path, config: Mapping[str, Any], generator_sha256: str, auditor_sha256: str) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L1430](../src/april_repro/query202_human_adjudication_audit.py#L1430) | function/method | <code>_reopen_test_attestation_closure_file(root: Path, initial: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1452](../src/april_repro/query202_human_adjudication_audit.py#L1452) | function/method | <code>_load_contract(root: Path, config_path: Path) -&gt; dict[str, Any]</code> |  |
| [L1817](../src/april_repro/query202_human_adjudication_audit.py#L1817) | function/method | <code>_artifact_file(directory: Path, value: object, label: str) -&gt; Path</code> |  |
| [L1823](../src/april_repro/query202_human_adjudication_audit.py#L1823) | function/method | <code>_source_inventory(root: Path, contract: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1989](../src/april_repro/query202_human_adjudication_audit.py#L1989) | function/method | <code>_semantic_set_hash(items: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L2009](../src/april_repro/query202_human_adjudication_audit.py#L2009) | function/method | <code>_route_set_hash(items: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L2021](../src/april_repro/query202_human_adjudication_audit.py#L2021) | function/method | <code>_parse_semantic_template(records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]) -&gt; list[dict[str, Any]]</code> |  |
| [L2119](../src/april_repro/query202_human_adjudication_audit.py#L2119) | function/method | <code>_parse_route_template(records: Sequence[Mapping[str, Any]], section: Mapping[str, Any]) -&gt; tuple[list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L2318](../src/april_repro/query202_human_adjudication_audit.py#L2318) | function/method | <code>_semantic_default(review_id: str, semantic: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2346](../src/april_repro/query202_human_adjudication_audit.py#L2346) | function/method | <code>_route_default(review_id: str) -&gt; dict[str, Any]</code> |  |
| [L2363](../src/april_repro/query202_human_adjudication_audit.py#L2363) | function/method | <code>_source_batch_expected(kind: str, batch_index: int, batch_count: int, items: Sequence[Mapping[str, Any]], memberships: Sequence[Mapping[str, Any]]=()) -&gt; list[Mapping[str, Any]]</code> |  |
| [L2391](../src/april_repro/query202_human_adjudication_audit.py#L2391) | function/method | <code>_validate_source_batch(records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int, items: Sequence[Mapping[str, Any]], memberships: Sequence[Mapping[str, Any]]=()) -&gt; None</code> |  |
| [L2408](../src/april_repro/query202_human_adjudication_audit.py#L2408) | function/method | <code>_evidence_refs(value: object, registry: Mapping[str, Mapping[str, Any]], *, required: bool, review_id: str &#124; None=None) -&gt; list[str]</code> |  |
| [L2440](../src/april_repro/query202_human_adjudication_audit.py#L2440) | function/method | <code>_revision_common(record: Mapping[str, Any], expected_type: str, pattern: re.Pattern[str]) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L2459](../src/april_repro/query202_human_adjudication_audit.py#L2459) | function/method | <code>_validate_dimensions(dimensions: object, semantic: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]], review_status: str, review_id: str &#124; None) -&gt; None</code> |  |
| [L2527](../src/april_repro/query202_human_adjudication_audit.py#L2527) | function/method | <code>_validate_semantic_revision(raw_record: Mapping[str, Any], semantic: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]], *, bind_source: bool=True) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L2585](../src/april_repro/query202_human_adjudication_audit.py#L2585) | function/method | <code>_validate_route_revision(raw_record: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[str, int, str &#124; None]</code> |  |
| [L2648](../src/april_repro/query202_human_adjudication_audit.py#L2648) | function/method | <code>_active_batch_hash(kind: str, batch_index: int, active: Mapping[str, Mapping[str, Any]]) -&gt; str</code> |  |
| [L2665](../src/april_repro/query202_human_adjudication_audit.py#L2665) | function/method | <code>_validate_decision_ledger(records: Sequence[Mapping[str, Any]], kind: str, batch_index: int, batch_count: int, source_relative: str, source_snapshot: Mapping[str, Any], expected_ids: Sequence[str], contract: Mapping[str, Any], registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], str, set[str], dict[tuple[str, str, int], Mapping[str, Any]]]</code> |  |
| [L2798](../src/april_repro/query202_human_adjudication_audit.py#L2798) | function/method | <code>_validate_evidence_registry(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], all_review_ids: set[str], workspace_snapshots: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, dict[str, Any]], set[str]]</code> |  |
| [L2940](../src/april_repro/query202_human_adjudication_audit.py#L2940) | function/method | <code>_scan_local_evidence_index(snapshot: Mapping[str, Any], config: Mapping[str, Any], registry: dict[str, dict[str, Any]], semantic_count: int) -&gt; None</code> | Independently hash, decode, and resolve the entire private index. |
| [L3019](../src/april_repro/query202_human_adjudication_audit.py#L3019) | function/method | <code>_audit_local_evidence_source_to_index(source_inventory: Mapping[str, Any], config: Mapping[str, Any], semantic_items: Sequence[Mapping[str, Any]], index_snapshot: Mapping[str, Any]) -&gt; dict[str, Any]</code> | Independently derive and compare every private bridge-index record. |
| [L3116](../src/april_repro/query202_human_adjudication_audit.py#L3116) | function/method | <code>_audit_local_evidence_source_to_index._valid_stream_hash(value: object) -&gt; bool</code> |  |
| [L3119](../src/april_repro/query202_human_adjudication_audit.py#L3119) | function/method | <code>_audit_local_evidence_source_to_index._compare_bridge_record(record: Mapping[str, Any]) -&gt; None</code> |  |
| [L3171](../src/april_repro/query202_human_adjudication_audit.py#L3171) | function/method | <code>_audit_local_evidence_source_to_index._handle(record: Mapping[str, Any]) -&gt; None</code> |  |
| [L3340](../src/april_repro/query202_human_adjudication_audit.py#L3340) | function/method | <code>_audit_local_evidence_source_to_index._consume(raw: bytes) -&gt; None</code> |  |
| [L3475](../src/april_repro/query202_human_adjudication_audit.py#L3475) | function/method | <code>_validate_group_ledger(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], semantic_active: Mapping[str, Mapping[str, Any]], registry: Mapping[str, Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], set[str], dict[tuple[str, str, int], Mapping[str, Any]]]</code> |  |
| [L3647](../src/april_repro/query202_human_adjudication_audit.py#L3647) | function/method | <code>_validate_attestations(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], bindings: Mapping[tuple[str, int], Mapping[str, Any]], group_sha256: str) -&gt; tuple[set[str], dict[str, Mapping[str, Any]], dict[tuple[str, int], str]]</code> |  |
| [L3756](../src/april_repro/query202_human_adjudication_audit.py#L3756) | function/method | <code>_walk_workspace(workspace: Path, *, root: Path &#124; None=None) -&gt; tuple[set[str], list[Path]]</code> | Inventory a private tree through no-follow directory descriptors. |
| [L3774](../src/april_repro/query202_human_adjudication_audit.py#L3774) | function/method | <code>_walk_workspace.visit(current: int, relative_parts: tuple[str, ...]) -&gt; None</code> |  |
| [L3842](../src/april_repro/query202_human_adjudication_audit.py#L3842) | function/method | <code>_workspace_paths(batch_count: int) -&gt; dict[str, list[str]]</code> |  |
| [L3864](../src/april_repro/query202_human_adjudication_audit.py#L3864) | function/method | <code>_utc_datetime(value: str) -&gt; datetime</code> |  |
| [L3868](../src/april_repro/query202_human_adjudication_audit.py#L3868) | function/method | <code>_revision_event_subject(binding: Mapping[str, Any]) -&gt; str</code> |  |
| [L3877](../src/april_repro/query202_human_adjudication_audit.py#L3877) | function/method | <code>_attestation_event_subject(binding: Mapping[str, Any]) -&gt; str</code> |  |
| [L3881](../src/april_repro/query202_human_adjudication_audit.py#L3881) | function/method | <code>_validate_revision_events(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], expected: Mapping[tuple[str, str, int], Mapping[str, Any]]) -&gt; tuple[dict[str, Mapping[str, Any]], set[str]]</code> |  |
| [L3950](../src/april_repro/query202_human_adjudication_audit.py#L3950) | function/method | <code>_active_workspace_state_hash(batch_bindings: Mapping[tuple[str, int], Mapping[str, Any]], groups: Mapping[str, Mapping[str, Any]], current_attestations: Mapping[tuple[str, int], str]) -&gt; str</code> |  |
| [L3987](../src/april_repro/query202_human_adjudication_audit.py#L3987) | function/method | <code>_validate_workspace_events(records: Sequence[Mapping[str, Any]], contract: Mapping[str, Any], manifest: Mapping[str, Any], revision_events: Mapping[str, Mapping[str, Any]], attestations: Mapping[str, Mapping[str, Any]], active_state_sha256: str, reviewer_id: str) -&gt; int</code> |  |
| [L4143](../src/april_repro/query202_human_adjudication_audit.py#L4143) | function/method | <code>_validate_manifest(manifest: Mapping[str, Any], root: Path, workspace: Path, config_path: Path, contract: Mapping[str, Any], semantic_count: int, route_count: int, membership_count: int) -&gt; tuple[dict[str, Mapping[str, Any]], set[str]]</code> |  |
| [L4325](../src/april_repro/query202_human_adjudication_audit.py#L4325) | function/method | <code>_finish_closure(contract: Mapping[str, Any], source_inventory: Mapping[str, Any], workspace: Path, workspace_directory_snapshot: Mapping[str, Any], directory_snapshots: Mapping[str, Mapping[str, Any]], file_snapshots: Mapping[str, Mapping[str, Any]]) -&gt; None</code> |  |
| [L4407](../src/april_repro/query202_human_adjudication_audit.py#L4407) | function/method | <code>audit_human_adjudication_workspace(root: Path, workspace_directory: Path, config_path: Path=CONFIG_PATH) -&gt; dict[str, Any]</code> | Independently audit a formal, human-complete private workspace. |
| [L4786](../src/april_repro/query202_human_adjudication_audit.py#L4786) | function/method | <code>_validate_final_contract(contract: Mapping[str, Any]) -&gt; None</code> |  |
| [L4884](../src/april_repro/query202_human_adjudication_audit.py#L4884) | function/method | <code>_snapshot_flat_artifact(root: Path, artifact: Path, expected: set[str], *, retain_payload: bool) -&gt; tuple[dict[str, Any], dict[str, dict[str, Any]]]</code> |  |
| [L4916](../src/april_repro/query202_human_adjudication_audit.py#L4916) | function/method | <code>_artifact_gzip_records(snapshot: Mapping[str, Any], label: str) -&gt; tuple[bytes, list[Mapping[str, Any]]]</code> |  |
| [L4941](../src/april_repro/query202_human_adjudication_audit.py#L4941) | function/method | <code>_framed_projection(begin: Mapping[str, Any], body: Sequence[Mapping[str, Any]], end_type: str, hash_version: str) -&gt; tuple[list[Mapping[str, Any]], str]</code> |  |
| [L4960](../src/april_repro/query202_human_adjudication_audit.py#L4960) | function/method | <code>_active_projection(records: Sequence[Mapping[str, Any]], identifier_key: str) -&gt; dict[str, Mapping[str, Any]]</code> |  |
| [L4983](../src/april_repro/query202_human_adjudication_audit.py#L4983) | function/method | <code>_workspace_projection_for_final(root: Path, workspace_relative: Path, declared_files: object, batch_count: int) -&gt; dict[str, Any]</code> |  |
| [L5162](../src/april_repro/query202_human_adjudication_audit.py#L5162) | function/method | <code>_expected_compiled_outputs(projection: Mapping[str, Any], contract: Mapping[str, Any], created_at: str) -&gt; dict[str, Any]</code> |  |
| [L5432](../src/april_repro/query202_human_adjudication_audit.py#L5432) | function/method | <code>_workspace_inventory_records(snapshots: Mapping[str, Mapping[str, Any]]) -&gt; list[dict[str, Any]]</code> |  |
| [L5447](../src/april_repro/query202_human_adjudication_audit.py#L5447) | function/method | <code>_expected_final_manifest(root: Path, artifact_relative: Path, projection: Mapping[str, Any], contract: Mapping[str, Any], output_metadata: Mapping[str, Mapping[str, Any]], summary_metadata: Mapping[str, Any], decision_hashes: Mapping[str, Any], created_at: str) -&gt; dict[str, Any]</code> |  |
| [L5575](../src/april_repro/query202_human_adjudication_audit.py#L5575) | function/method | <code>_finish_final_dependency_closure(contract: Mapping[str, Any], source_inventory: Mapping[str, Any], projection: Mapping[str, Any], artifact: Path, artifact_files: Mapping[str, Mapping[str, Any]], expected_artifact_names: set[str]) -&gt; None</code> |  |
| [L5678](../src/april_repro/query202_human_adjudication_audit.py#L5678) | function/method | <code>_snapshot_regular_at(directory_descriptor: int, name: str, label: str) -&gt; dict[str, Any]</code> |  |
| [L5730](../src/april_repro/query202_human_adjudication_audit.py#L5730) | function/method | <code>_unlink_if_identity_at(directory_descriptor: int, name: str, expected_identity: tuple[int, int]) -&gt; None</code> |  |
| [L5741](../src/april_repro/query202_human_adjudication_audit.py#L5741) | function/method | <code>_atomic_add_final_audit(root: Path, artifact: Path, payload: bytes, initial_directory: Mapping[str, Any], verify_published: Callable[[], None], failure_hook: Callable[[str], None] &#124; None=None) -&gt; None</code> |  |
| [L5927](../src/april_repro/query202_human_adjudication_audit.py#L5927) | function/method | <code>audit_compiled_human_adjudication_artifact(root: Path, artifact_directory: Path, config_path: Path=CONFIG_PATH, *, audited_at_utc: str &#124; None=None, _failure_hook: Callable[[str], None] &#124; None=None) -&gt; dict[str, Any]</code> | Audit seven compiled outputs and atomically add &#96;&#96;audit-summary.json&#96;&#96;. |
| [L6146](../src/april_repro/query202_human_adjudication_audit.py#L6146) | function/method | <code>audit_compiled_human_adjudication_artifact.verify_published() -&gt; None</code> |  |

<a id="module-d1bc69c282be"></a>

## src/april_repro/query202_human_adjudication_finalize.py

[Open source](../src/april_repro/query202_human_adjudication_finalize.py)

Source module docstring:

> Compile and separately freeze the Query-202 human adjudication artifact. The compiler consumes only a formal workspace which the workspace validator reports as &#96;&#96;human_review_complete_unfrozen&#96;&#96;. It emits a private, immutable projection of the active human decisions. The later freeze operation accepts only an audit made by the independently bundled final-artifact auditor and adds one file; it never edits an output that was audited. This module is part of the generator lineage. It may use the workspace validator, but the independent auditor must not import this module or the workspace generator/validator.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L108](../src/april_repro/query202_human_adjudication_finalize.py#L108) | class | <code>HumanAdjudicationFinalizeError(RuntimeError)</code> | Fail-closed compilation, audit-binding, or freeze error. |
| [L112](../src/april_repro/query202_human_adjudication_finalize.py#L112) | function/method | <code>_fail(message: str) -&gt; None</code> |  |
| [L116](../src/april_repro/query202_human_adjudication_finalize.py#L116) | function/method | <code>_canonical_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L129](../src/april_repro/query202_human_adjudication_finalize.py#L129) | function/method | <code>_pretty_json(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L145](../src/april_repro/query202_human_adjudication_finalize.py#L145) | function/method | <code>_strict_json(raw: bytes, label: str) -&gt; Mapping[str, Any]</code> |  |
| [L146](../src/april_repro/query202_human_adjudication_finalize.py#L146) | function/method | <code>_strict_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L154](../src/april_repro/query202_human_adjudication_finalize.py#L154) | function/method | <code>_strict_json.reject(_: str) -&gt; None</code> |  |
| [L174](../src/april_repro/query202_human_adjudication_finalize.py#L174) | function/method | <code>_now_utc() -&gt; str</code> |  |
| [L180](../src/april_repro/query202_human_adjudication_finalize.py#L180) | function/method | <code>_require_utc(value: str &#124; None, label: str) -&gt; str</code> |  |
| [L187](../src/april_repro/query202_human_adjudication_finalize.py#L187) | function/method | <code>_timestamp_directory(value: str) -&gt; str</code> |  |
| [L194](../src/april_repro/query202_human_adjudication_finalize.py#L194) | function/method | <code>_valid_artifact_leaf(value: str) -&gt; bool</code> |  |
| [L202](../src/april_repro/query202_human_adjudication_finalize.py#L202) | function/method | <code>_sha(raw: bytes) -&gt; str</code> |  |
| [L206](../src/april_repro/query202_human_adjudication_finalize.py#L206) | function/method | <code>_record_hash(record: Mapping[str, Any]) -&gt; str</code> |  |
| [L210](../src/april_repro/query202_human_adjudication_finalize.py#L210) | function/method | <code>_sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L223](../src/april_repro/query202_human_adjudication_finalize.py#L223) | function/method | <code>_ndjson(records: Sequence[Mapping[str, Any]]) -&gt; bytes</code> |  |
| [L227](../src/april_repro/query202_human_adjudication_finalize.py#L227) | function/method | <code>_single_member_gzip(raw: bytes) -&gt; bytes</code> |  |
| [L236](../src/april_repro/query202_human_adjudication_finalize.py#L236) | function/method | <code>_verify_single_member_gzip(stored: bytes, raw: bytes, label: str) -&gt; None</code> |  |
| [L251](../src/april_repro/query202_human_adjudication_finalize.py#L251) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; dict[str, Any]</code> |  |
| [L273](../src/april_repro/query202_human_adjudication_finalize.py#L273) | function/method | <code>_write_private_at(directory_descriptor: int, name: str, payload: bytes) -&gt; dict[str, Any]</code> |  |
| [L305](../src/april_repro/query202_human_adjudication_finalize.py#L305) | function/method | <code>_write_gzip(path: Path, records: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L321](../src/april_repro/query202_human_adjudication_finalize.py#L321) | function/method | <code>_write_gzip_at(directory_descriptor: int, name: str, records: Sequence[Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L339](../src/april_repro/query202_human_adjudication_finalize.py#L339) | function/method | <code>_snapshot_regular_at(directory_descriptor: int, name: str) -&gt; dict[str, Any]</code> |  |
| [L381](../src/april_repro/query202_human_adjudication_finalize.py#L381) | function/method | <code>_new_private_directory_at(parent_descriptor: int, prefix: str) -&gt; tuple[str, int]</code> |  |
| [L394](../src/april_repro/query202_human_adjudication_finalize.py#L394) | function/method | <code>_remove_tree_if_identity_at(parent_descriptor: int, name: str, expected_identity: tuple[int, int]) -&gt; None</code> | Remove only the controlled tree; preserve any raced-in replacement. |
| [L409](../src/april_repro/query202_human_adjudication_finalize.py#L409) | function/method | <code>_unlink_if_identity_at(parent_descriptor: int, name: str, expected_identity: tuple[int, int]) -&gt; None</code> |  |
| [L422](../src/april_repro/query202_human_adjudication_finalize.py#L422) | function/method | <code>_rename_directory_noreplace(source_parent_descriptor: int, source_name: str, destination_parent_descriptor: int, destination_name: str) -&gt; None</code> | Atomically rename without ever replacing an existing destination. |
| [L467](../src/april_repro/query202_human_adjudication_finalize.py#L467) | function/method | <code>_call_hook(hook: FailureHook &#124; None, point: str) -&gt; None</code> |  |
| [L472](../src/april_repro/query202_human_adjudication_finalize.py#L472) | function/method | <code>_assert_independent_auditor_imports(bundle: Mapping[str, Any]) -&gt; None</code> |  |
| [L481](../src/april_repro/query202_human_adjudication_finalize.py#L481) | function/method | <code>_assert_independent_auditor_imports.names_generator_helper(name: str) -&gt; bool</code> |  |
| [L506](../src/april_repro/query202_human_adjudication_finalize.py#L506) | function/method | <code>_load_contract(root: Path, config_path: Path) -&gt; dict[str, Any]</code> |  |
| [L640](../src/april_repro/query202_human_adjudication_finalize.py#L640) | function/method | <code>_finish_auditor_closure(root: Path, bundle: Mapping[str, Any]) -&gt; None</code> |  |
| [L655](../src/april_repro/query202_human_adjudication_finalize.py#L655) | function/method | <code>_snapshot_test_gate_closure(root: Path, contract: Mapping[str, Any]) -&gt; dict[str, Any]</code> | Independently retain descriptor snapshots of the attested execution closure. |
| [L737](../src/april_repro/query202_human_adjudication_finalize.py#L737) | function/method | <code>_snapshot_runtime_locator(root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Bind the project-local interpreter locator without following its leaf. |
| [L803](../src/april_repro/query202_human_adjudication_finalize.py#L803) | function/method | <code>_runtime_locator_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L820](../src/april_repro/query202_human_adjudication_finalize.py#L820) | function/method | <code>_finish_test_gate_closure(root: Path, closure: Mapping[str, Any]) -&gt; None</code> |  |
| [L866](../src/april_repro/query202_human_adjudication_finalize.py#L866) | function/method | <code>_safe_project_directory(root: Path, relative: Path, label: str, *, must_exist: bool) -&gt; Path</code> |  |
| [L877](../src/april_repro/query202_human_adjudication_finalize.py#L877) | function/method | <code>_snapshot_workspace(path: Path, *, retain_payload: bool) -&gt; dict[str, Any]</code> |  |
| [L917](../src/april_repro/query202_human_adjudication_finalize.py#L917) | function/method | <code>_same_snapshot(first: Mapping[str, Any], second: Mapping[str, Any]) -&gt; bool</code> |  |
| [L921](../src/april_repro/query202_human_adjudication_finalize.py#L921) | function/method | <code>_assert_workspace_closure(path: Path, initial: Mapping[str, Any]) -&gt; None</code> |  |
| [L943](../src/april_repro/query202_human_adjudication_finalize.py#L943) | function/method | <code>_records(snapshot: Mapping[str, Any], label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L952](../src/april_repro/query202_human_adjudication_finalize.py#L952) | function/method | <code>_active(records: Sequence[Mapping[str, Any]], id_key: str) -&gt; dict[str, Mapping[str, Any]]</code> |  |
| [L966](../src/april_repro/query202_human_adjudication_finalize.py#L966) | function/method | <code>_workspace_projection(snapshots: Mapping[str, Mapping[str, Any]], config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1041](../src/april_repro/query202_human_adjudication_finalize.py#L1041) | function/method | <code>_framed_records(begin: Mapping[str, Any], body: Sequence[Mapping[str, Any]], end_type: str, hash_version: str) -&gt; tuple[list[Mapping[str, Any]], str]</code> |  |
| [L1060](../src/april_repro/query202_human_adjudication_finalize.py#L1060) | function/method | <code>_build_outputs(projection: Mapping[str, Any], contract: Mapping[str, Any], created_at: str) -&gt; dict[str, Any]</code> |  |
| [L1286](../src/april_repro/query202_human_adjudication_finalize.py#L1286) | function/method | <code>_workspace_inventory_for_manifest(snapshots: Mapping[str, Mapping[str, Any]]) -&gt; list[dict[str, Any]]</code> |  |
| [L1301](../src/april_repro/query202_human_adjudication_finalize.py#L1301) | function/method | <code>_inventory_hash(version: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L1305](../src/april_repro/query202_human_adjudication_finalize.py#L1305) | function/method | <code>_workspace_lineage(workspace_relative: Path, snapshots: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1333](../src/april_repro/query202_human_adjudication_finalize.py#L1333) | function/method | <code>_artifact_manifest(root: Path, destination: Path, workspace_relative: Path, workspace_snapshots: Mapping[str, Mapping[str, Any]], output_meta: Mapping[str, Mapping[str, Any]], summary_meta: Mapping[str, Any], decision_hashes: Mapping[str, Any], contract: Mapping[str, Any], created_at: str) -&gt; dict[str, Any]</code> |  |
| [L1420](../src/april_repro/query202_human_adjudication_finalize.py#L1420) | function/method | <code>_assert_temporary_outputs_at(directory_descriptor: int, expected_meta: Mapping[str, Mapping[str, Any]]) -&gt; None</code> |  |
| [L1437](../src/april_repro/query202_human_adjudication_finalize.py#L1437) | function/method | <code>compile_human_adjudication_artifact(root: Path, workspace_directory: Path, config_path: Path=CONFIG_PATH, *, created_at_utc: str &#124; None=None, _failure_hook: FailureHook &#124; None=None) -&gt; dict[str, Any]</code> | Compile a complete formal workspace into seven private outputs. |
| [L1704](../src/april_repro/query202_human_adjudication_finalize.py#L1704) | function/method | <code>_snapshot_artifact(artifact: Path, expected: set[str]) -&gt; tuple[dict[str, Any], dict[str, dict[str, Any]]]</code> |  |
| [L1741](../src/april_repro/query202_human_adjudication_finalize.py#L1741) | function/method | <code>_assert_artifact_file_closure(artifact: Path, initial: Mapping[str, Mapping[str, Any]], expected: set[str]) -&gt; None</code> |  |
| [L1762](../src/april_repro/query202_human_adjudication_finalize.py#L1762) | function/method | <code>_expected_audited_files(snapshots: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L1771](../src/april_repro/query202_human_adjudication_finalize.py#L1771) | function/method | <code>_validate_retained_workspace(root: Path, manifest_workspace: Mapping[str, Any], contract: Mapping[str, Any]) -&gt; tuple[Path, dict[str, Any]]</code> |  |
| [L1856](../src/april_repro/query202_human_adjudication_finalize.py#L1856) | function/method | <code>_validate_audit(audit: Mapping[str, Any], artifact_relative: Path, snapshots: Mapping[str, Mapping[str, Any]], manifest: Mapping[str, Any], contract: Mapping[str, Any]) -&gt; None</code> |  |
| [L1951](../src/april_repro/query202_human_adjudication_finalize.py#L1951) | function/method | <code>freeze_human_adjudication_artifact(root: Path, artifact_directory: Path, config_path: Path=CONFIG_PATH, *, frozen_at_utc: str &#124; None=None, _failure_hook: FailureHook &#124; None=None) -&gt; dict[str, Any]</code> | Add one freeze manifest after an exact independent final audit. |

<a id="module-29f5b6dd9a1f"></a>

## src/april_repro/query202_human_adjudication_preregistration.py

[Open source](../src/april_repro/query202_human_adjudication_preregistration.py)

Source module docstring:

> Fail-closed proposal report for Query-202 human adjudication. The report authenticates the public lineage documents and hashes the three private source streams as opaque files. It never decompresses or parses those streams. A valid proposal is deliberately distinct from permission to create an adjudication workspace.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L1069](../src/april_repro/query202_human_adjudication_preregistration.py#L1069) | class | <code>HumanAdjudicationPreregistrationError(RuntimeError)</code> | Raised when the proposal cannot be read without ambiguity. |
| [L1073](../src/april_repro/query202_human_adjudication_preregistration.py#L1073) | function/method | <code>_strict_equal(actual: object, expected: object) -&gt; bool</code> |  |
| [L1089](../src/april_repro/query202_human_adjudication_preregistration.py#L1089) | function/method | <code>_as_mapping(value: object) -&gt; Mapping[str, Any]</code> |  |
| [L1093](../src/april_repro/query202_human_adjudication_preregistration.py#L1093) | function/method | <code>_validate_exact_mapping(actual: object, expected: Mapping[str, Any], label: str, errors: list[str]) -&gt; None</code> |  |
| [L1113](../src/april_repro/query202_human_adjudication_preregistration.py#L1113) | function/method | <code>_safe_relative(value: object) -&gt; bool</code> |  |
| [L1120](../src/april_repro/query202_human_adjudication_preregistration.py#L1120) | function/method | <code>_relative_parts(relative: object) -&gt; tuple[str, ...]</code> |  |
| [L1129](../src/april_repro/query202_human_adjudication_preregistration.py#L1129) | function/method | <code>_directory_open_flags() -&gt; int</code> |  |
| [L1135](../src/april_repro/query202_human_adjudication_preregistration.py#L1135) | function/method | <code>_open_directory_chain(root: Path, parts: Sequence[str]) -&gt; list[int]</code> | Open each directory from a trusted root without following symlinks. |
| [L1180](../src/april_repro/query202_human_adjudication_preregistration.py#L1180) | function/method | <code>_same_snapshot(left: os.stat_result, right: os.stat_result) -&gt; bool</code> |  |
| [L1200](../src/april_repro/query202_human_adjudication_preregistration.py#L1200) | function/method | <code>_snapshot_regular_file(root: Path, relative: object, *, retain_payload: bool, maximum_bytes: int &#124; None=None) -&gt; dict[str, Any]</code> |  |
| [L1263](../src/april_repro/query202_human_adjudication_preregistration.py#L1263) | function/method | <code>_snapshot_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L1282](../src/april_repro/query202_human_adjudication_preregistration.py#L1282) | function/method | <code>_directory_seal(root: Path, relative: object) -&gt; dict[str, Any]</code> |  |
| [L1298](../src/april_repro/query202_human_adjudication_preregistration.py#L1298) | function/method | <code>_strict_json(payload: bytes) -&gt; Any</code> |  |
| [L1299](../src/april_repro/query202_human_adjudication_preregistration.py#L1299) | function/method | <code>_strict_json.object_pairs(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1310](../src/april_repro/query202_human_adjudication_preregistration.py#L1310) | function/method | <code>_read_config_snapshot(root: Path) -&gt; tuple[dict[str, Any], str, dict[str, Any]]</code> |  |
| [L1324](../src/april_repro/query202_human_adjudication_preregistration.py#L1324) | function/method | <code>read_query202_human_adjudication_preregistration(root: Path) -&gt; dict[str, Any]</code> |  |
| [L1329](../src/april_repro/query202_human_adjudication_preregistration.py#L1329) | function/method | <code>_is_sha256(value: object) -&gt; bool</code> |  |
| [L1337](../src/april_repro/query202_human_adjudication_preregistration.py#L1337) | function/method | <code>_validate_test_attestation_contract(value: object, *, candidate_contract: bool, errors: list[str]) -&gt; None</code> |  |
| [L1392](../src/april_repro/query202_human_adjudication_preregistration.py#L1392) | function/method | <code>validate_query202_human_adjudication_preregistration(config: Mapping[str, Any]) -&gt; list[str]</code> | Validate the exact v1 proposal, freeze candidate, or frozen contract. |
| [L1537](../src/april_repro/query202_human_adjudication_preregistration.py#L1537) | function/method | <code>_implementation_bundle_snapshot(root: Path, paths: Sequence[str]) -&gt; tuple[str, dict[str, tuple[str, dict[str, Any]]]]</code> |  |
| [L1557](../src/april_repro/query202_human_adjudication_preregistration.py#L1557) | function/method | <code>implementation_bundle_sha256(root: Path, paths: Sequence[str]) -&gt; str</code> |  |
| [L1562](../src/april_repro/query202_human_adjudication_preregistration.py#L1562) | function/method | <code>_contract_projection(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> | Return the stable contract covered by the synthetic-test attestation. |
| [L1598](../src/april_repro/query202_human_adjudication_preregistration.py#L1598) | function/method | <code>scientific_contract_sha256(config: Mapping[str, Any]) -&gt; str</code> |  |
| [L1608](../src/april_repro/query202_human_adjudication_preregistration.py#L1608) | function/method | <code>_canonical_json_bytes(value: object) -&gt; bytes</code> |  |
| [L1620](../src/april_repro/query202_human_adjudication_preregistration.py#L1620) | function/method | <code>_verify_test_attestation(root: Path, config: Mapping[str, Any], actual_bundle_hashes: Mapping[str, object]) -&gt; tuple[bool, list[str], dict[str, Any], dict[str, tuple[str, dict[str, Any]]]]</code> | Verify the project-local attestation without exposing per-test details. |
| [L1804](../src/april_repro/query202_human_adjudication_preregistration.py#L1804) | function/method | <code>_ordered_test_ids_sha256(test_ids: Sequence[str]) -&gt; str</code> |  |
| [L1813](../src/april_repro/query202_human_adjudication_preregistration.py#L1813) | function/method | <code>_execution_snapshot_summary(config: Mapping[str, Any], snapshots: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, object]</code> |  |
| [L1846](../src/april_repro/query202_human_adjudication_preregistration.py#L1846) | function/method | <code>_python_runtime_snapshot(root: Path) -&gt; tuple[dict[str, object], dict[str, Any]]</code> |  |
| [L1877](../src/april_repro/query202_human_adjudication_preregistration.py#L1877) | function/method | <code>_snapshot_runtime_locator(root: Path) -&gt; tuple[dict[str, Any], Path]</code> | Bind the project-local runtime locator without following its leaf. |
| [L1930](../src/april_repro/query202_human_adjudication_preregistration.py#L1930) | function/method | <code>_runtime_locator_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> |  |
| [L1947](../src/april_repro/query202_human_adjudication_preregistration.py#L1947) | function/method | <code>_python_runtime_summary(root: Path) -&gt; dict[str, object]</code> |  |
| [L1952](../src/april_repro/query202_human_adjudication_preregistration.py#L1952) | function/method | <code>_resolved_runtime_identity(path: Path) -&gt; tuple[int, int]</code> |  |
| [L1960](../src/april_repro/query202_human_adjudication_preregistration.py#L1960) | function/method | <code>_copy_execution_snapshot(root: Path, snapshots: Mapping[str, Mapping[str, Any]], *, runtime_identity: tuple[int, int]) -&gt; tuple[Path, dict[str, dict[str, Any]]]</code> |  |
| [L2020](../src/april_repro/query202_human_adjudication_preregistration.py#L2020) | function/method | <code>_parse_successful_unittest_result(result: subprocess.CompletedProcess[str]) -&gt; tuple[int, tuple[str, ...]]</code> |  |
| [L2056](../src/april_repro/query202_human_adjudication_preregistration.py#L2056) | function/method | <code>_parse_successful_unittest_count(result: subprocess.CompletedProcess[str]) -&gt; int</code> | Compatibility wrapper retained for callers that only need the count. |
| [L2062](../src/april_repro/query202_human_adjudication_preregistration.py#L2062) | function/method | <code>build_test_attestation(root: Path) -&gt; dict[str, Any]</code> | Run the locked suite and return deterministic, private-safe evidence. |
| [L2234](../src/april_repro/query202_human_adjudication_preregistration.py#L2234) | function/method | <code>_check_equal(checks: dict[str, bool], errors: list[str], label: str, actual: object, expected: object) -&gt; None</code> |  |
| [L2247](../src/april_repro/query202_human_adjudication_preregistration.py#L2247) | function/method | <code>_git_ignored(root: Path, relative: str) -&gt; bool</code> |  |
| [L2260](../src/april_repro/query202_human_adjudication_preregistration.py#L2260) | function/method | <code>_public_stream_metadata(spec: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2272](../src/april_repro/query202_human_adjudication_preregistration.py#L2272) | function/method | <code>_verify_source_evidence(root: Path, errors: list[str]) -&gt; tuple[dict[str, bool], dict[str, tuple[str, dict[str, Any]]], dict[str, Any] &#124; None]</code> |  |
| [L2526](../src/april_repro/query202_human_adjudication_preregistration.py#L2526) | function/method | <code>_verify_ndc_decision(root: Path, errors: list[str]) -&gt; tuple[dict[str, bool], dict[str, tuple[str, dict[str, Any]]]]</code> |  |
| [L2613](../src/april_repro/query202_human_adjudication_preregistration.py#L2613) | function/method | <code>_verify_snapshot_closure(root: Path, initial_snapshots: Mapping[str, tuple[str, Mapping[str, Any]]], initial_artifact_directory: Mapping[str, Any] &#124; None, errors: list[str]) -&gt; dict[str, bool]</code> |  |
| [L2644](../src/april_repro/query202_human_adjudication_preregistration.py#L2644) | function/method | <code>query202_human_adjudication_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |

<a id="module-3c937a2924e2"></a>

## src/april_repro/query202_human_adjudication_writer.py

[Open source](../src/april_repro/query202_human_adjudication_writer.py)

Source module docstring:

> Apply human-authored Query-202 adjudication transactions safely. The request is a private, exact-schema JSON document. It contains the human reviewer's controlled clinical decisions, rationale, and times. This module only supplies mechanical sequence numbers, predecessor hashes, event-chain records, attestation bindings, and the optional terminal transition. Updates are made to a complete private sibling copy. The copy must pass the normal workspace validator before it can replace the live workspace through a single atomic directory exchange. Reports and exceptions never reproduce review IDs, source values, rationale, evidence paths, or document names.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L117](../src/april_repro/query202_human_adjudication_writer.py#L117) | class | <code>HumanAdjudicationWriterError(workspace_api.HumanAdjudicationError)</code> | A private authoring request or atomic workspace update failed closed. |
| [L121](../src/april_repro/query202_human_adjudication_writer.py#L121) | function/method | <code>_fail(message: str) -&gt; None</code> |  |
| [L125](../src/april_repro/query202_human_adjudication_writer.py#L125) | function/method | <code>_inject(point: str) -&gt; None</code> |  |
| [L131](../src/april_repro/query202_human_adjudication_writer.py#L131) | function/method | <code>_exact(value: object, fields: Iterable[str], label: str) -&gt; Mapping[str, Any]</code> |  |
| [L137](../src/april_repro/query202_human_adjudication_writer.py#L137) | function/method | <code>_strict_utc(value: object, label: str) -&gt; str</code> |  |
| [L144](../src/april_repro/query202_human_adjudication_writer.py#L144) | function/method | <code>_utc(value: str) -&gt; datetime</code> |  |
| [L148](../src/april_repro/query202_human_adjudication_writer.py#L148) | function/method | <code>_bounded_text(value: object, label: str, maximum: int=workspace_api.MAX_TEXT_BYTES) -&gt; str</code> |  |
| [L155](../src/april_repro/query202_human_adjudication_writer.py#L155) | function/method | <code>_sha(raw: bytes) -&gt; str</code> |  |
| [L159](../src/april_repro/query202_human_adjudication_writer.py#L159) | function/method | <code>_sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L172](../src/april_repro/query202_human_adjudication_writer.py#L172) | function/method | <code>_snapshot_bounded_file(path: Path, label: str, maximum_bytes: int, *, retain_payload: bool=False, require_nonempty: bool=False) -&gt; dict[str, Any]</code> | Snapshot one regular file without reading beyond its accepted bound. |
| [L270](../src/april_repro/query202_human_adjudication_writer.py#L270) | function/method | <code>_workspace_snapshot_pass(workspace: Path) -&gt; tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]]]</code> |  |
| [L299](../src/april_repro/query202_human_adjudication_writer.py#L299) | function/method | <code>_workspace_snapshot_hash(workspace: Path) -&gt; tuple[str, tuple[int, int], tuple[tuple[int, int], ...]]</code> |  |
| [L336](../src/april_repro/query202_human_adjudication_writer.py#L336) | function/method | <code>inspect_human_adjudication_workspace(root: Path, workspace_directory: Path, config_path: Path=CONFIG_PATH) -&gt; dict[str, Any]</code> | Return an aggregate-only authoring base report for a formal workspace. |
| [L378](../src/april_repro/query202_human_adjudication_writer.py#L378) | function/method | <code>_load_private_transaction(root: Path, relative: Path) -&gt; tuple[Mapping[str, Any], Mapping[str, Any]]</code> |  |
| [L404](../src/april_repro/query202_human_adjudication_writer.py#L404) | function/method | <code>_validate_transaction_envelope(transaction: Mapping[str, Any]) -&gt; tuple[Path, str, str, Mapping[str, Any]]</code> |  |
| [L432](../src/april_repro/query202_human_adjudication_writer.py#L432) | function/method | <code>_acquire_lock(root: Path, workspace: Path) -&gt; tuple[int, int, str, tuple[tuple[int, int], ...]]</code> |  |
| [L464](../src/april_repro/query202_human_adjudication_writer.py#L464) | function/method | <code>_assert_lock_closure(parent_fd: int, lock_fd: int, lock_name: str) -&gt; None</code> |  |
| [L482](../src/april_repro/query202_human_adjudication_writer.py#L482) | function/method | <code>_relative_parent_fd(base_fd: int, relative: Path) -&gt; tuple[int, str]</code> |  |
| [L503](../src/april_repro/query202_human_adjudication_writer.py#L503) | function/method | <code>_copy_regular_file(source_fd: int, source_name: str, destination_fd: int, destination_name: str) -&gt; None</code> |  |
| [L541](../src/april_repro/query202_human_adjudication_writer.py#L541) | function/method | <code>_copy_tree_fd(source_fd: int, destination_fd: int) -&gt; None</code> |  |
| [L569](../src/april_repro/query202_human_adjudication_writer.py#L569) | function/method | <code>_stage_workspace(parent_fd: int, workspace_name: str) -&gt; tuple[str, int, tuple[int, int]]</code> |  |
| [L606](../src/april_repro/query202_human_adjudication_writer.py#L606) | function/method | <code>_read_records(path: Path, label: str) -&gt; list[Mapping[str, Any]]</code> |  |
| [L613](../src/april_repro/query202_human_adjudication_writer.py#L613) | function/method | <code>_append_records(stage_fd: int, relative: str, records: Sequence[Mapping[str, Any]]) -&gt; None</code> |  |
| [L641](../src/april_repro/query202_human_adjudication_writer.py#L641) | function/method | <code>_versioned_document_total(workspace: Path) -&gt; int</code> | Return a closure-checked total for all imported workspace documents. |
| [L681](../src/april_repro/query202_human_adjudication_writer.py#L681) | function/method | <code>_snapshot_document_source(root: Path, source_relative: object, expected_sha256: object, live_workspace: Path) -&gt; tuple[Path, Mapping[str, Any]]</code> |  |
| [L723](../src/april_repro/query202_human_adjudication_writer.py#L723) | function/method | <code>_copy_document(root: Path, source_path: Path, initial: Mapping[str, Any], stage_fd: int, destination_relative: str) -&gt; int</code> |  |
| [L771](../src/april_repro/query202_human_adjudication_writer.py#L771) | function/method | <code>_preflight_document_additions(root: Path, additions: Sequence[object], live_workspace: Path) -&gt; tuple[dict[int, tuple[Path, Mapping[str, Any]]], int]</code> |  |
| [L799](../src/april_repro/query202_human_adjudication_writer.py#L799) | function/method | <code>_active_by_id(records: Sequence[Mapping[str, Any]], key: str) -&gt; dict[str, Mapping[str, Any]]</code> |  |
| [L808](../src/april_repro/query202_human_adjudication_writer.py#L808) | function/method | <code>_existing_reviewer(stage: Path, batch_count: int) -&gt; str &#124; None</code> |  |
| [L827](../src/april_repro/query202_human_adjudication_writer.py#L827) | function/method | <code>_registry_map(records: Sequence[Mapping[str, Any]]) -&gt; dict[str, Mapping[str, Any]]</code> |  |
| [L837](../src/april_repro/query202_human_adjudication_writer.py#L837) | function/method | <code>_latest_event_time(records: Sequence[Mapping[str, Any]]) -&gt; datetime &#124; None</code> |  |
| [L844](../src/april_repro/query202_human_adjudication_writer.py#L844) | function/method | <code>_make_revision_event(records: list[Mapping[str, Any]], *, revision_kind: str, subject_id: str, batch_index: int &#124; None, revision: int, revision_record: Mapping[str, Any], reviewer: str, recorded_at: str) -&gt; Mapping[str, Any]</code> |  |
| [L874](../src/april_repro/query202_human_adjudication_writer.py#L874) | function/method | <code>_make_workspace_event(records: list[Mapping[str, Any]], *, event_type: str, event_at: str, actor: str, subject_kind: str, subject_id: str, subject_sha256: str) -&gt; Mapping[str, Any]</code> |  |
| [L901](../src/april_repro/query202_human_adjudication_writer.py#L901) | function/method | <code>_ensure_event_time(last: datetime &#124; None, value: str, submitted: str) -&gt; datetime</code> |  |
| [L908](../src/april_repro/query202_human_adjudication_writer.py#L908) | function/method | <code>_prepare_evidence(root: Path, stage_fd: int, additions: Sequence[object], existing_records: list[Mapping[str, Any]], document_preflights: Mapping[int, tuple[Path, Mapping[str, Any]]]) -&gt; tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]], int, int]</code> |  |
| [L981](../src/april_repro/query202_human_adjudication_writer.py#L981) | function/method | <code>_batch_index(review_id: str, batch_size: int) -&gt; int</code> |  |
| [L985](../src/april_repro/query202_human_adjudication_writer.py#L985) | function/method | <code>_post_batch_bindings(stage: Path, batch_count: int) -&gt; tuple[dict[tuple[str, int], dict[str, Any]], dict[tuple[str, int], dict[str, Mapping[str, Any]]]]</code> |  |
| [L1013](../src/april_repro/query202_human_adjudication_writer.py#L1013) | function/method | <code>_current_attestations(records: Sequence[Mapping[str, Any]], bindings: Mapping[tuple[str, int], Mapping[str, Any]], group_sha: str) -&gt; dict[tuple[str, int], str]</code> |  |
| [L1036](../src/april_repro/query202_human_adjudication_writer.py#L1036) | function/method | <code>_apply_to_stage(root: Path, stage_relative: Path, stage_fd: int, reviewer: str, operations: Mapping[str, Any], contract: Mapping[str, Any], document_preflights: Mapping[int, tuple[Path, Mapping[str, Any]]], expected_existing_document_bytes: int, expected_imported_document_bytes: int) -&gt; dict[str, Any]</code> |  |
| [L1437](../src/april_repro/query202_human_adjudication_writer.py#L1437) | function/method | <code>_exchange_directories(parent_fd: int, left: str, right: str) -&gt; None</code> |  |
| [L1470](../src/april_repro/query202_human_adjudication_writer.py#L1470) | function/method | <code>_named_identity(parent_fd: int, name: str) -&gt; tuple[int, int]</code> |  |
| [L1477](../src/april_repro/query202_human_adjudication_writer.py#L1477) | function/method | <code>_recover_stale_stages(root: Path, workspace_relative: Path, config_path: Path, parent_fd: int, parent_chain: tuple[tuple[int, int], ...]) -&gt; Mapping[str, Any] &#124; None</code> | Recover only states made unambiguous by the atomically named live tree. |
| [L1518](../src/april_repro/query202_human_adjudication_writer.py#L1518) | function/method | <code>_assert_transaction_closure(root: Path, snapshot: Mapping[str, Any]) -&gt; None</code> |  |
| [L1537](../src/april_repro/query202_human_adjudication_writer.py#L1537) | function/method | <code>apply_human_adjudication_transaction(root: Path, transaction_path: Path, config_path: Path=CONFIG_PATH) -&gt; dict[str, Any]</code> | Apply one exact human-authored transaction by validated atomic exchange. |

<a id="module-8e0fa73d6670"></a>

## src/april_repro/query202_ndc_evidence_mode_preregistration.py

[Open source](../src/april_repro/query202_ndc_evidence_mode_preregistration.py)

Source module docstring:

> Fail-closed freeze report for the Query-202 NDC evidence mode. This component verifies whole-file and public-lineage evidence only. It never decompresses, parses, or emits a row from the private NDC handoff.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L171](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L171) | class | <code>NdcEvidenceModeError(RuntimeError)</code> | Raised when a safe, aggregate-only report cannot be produced. |
| [L175](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L175) | function/method | <code>_strict_equal(actual: object, expected: object) -&gt; bool</code> |  |
| [L194](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L194) | function/method | <code>_validate_exact_mapping(actual: object, expected: Mapping[str, Any], label: str, errors: list[str]) -&gt; None</code> |  |
| [L214](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L214) | function/method | <code>_safe_relative(value: object) -&gt; bool</code> |  |
| [L221](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L221) | function/method | <code>_project_path(root: Path, relative: object) -&gt; Path</code> |  |
| [L234](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L234) | function/method | <code>_same_snapshot(left: os.stat_result, right: os.stat_result) -&gt; bool</code> |  |
| [L248](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L248) | function/method | <code>_snapshot_regular_file(root: Path, relative: object, *, retain_payload: bool) -&gt; dict[str, Any]</code> |  |
| [L296](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L296) | function/method | <code>_snapshot_seal(snapshot: Mapping[str, Any]) -&gt; tuple[object, ...]</code> | Return the fields that must remain identical across the full report. |
| [L303](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L303) | function/method | <code>_directory_seal(root: Path, relative: object) -&gt; dict[str, Any]</code> | Bind directory identity and mode without relying on directory mtime. |
| [L315](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L315) | function/method | <code>_strict_json(payload: bytes) -&gt; Any</code> |  |
| [L316](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L316) | function/method | <code>_strict_json.object_pairs(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L328](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L328) | function/method | <code>_read_config_snapshot(root: Path) -&gt; tuple[dict[str, Any], str, dict[str, Any]]</code> |  |
| [L342](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L342) | function/method | <code>read_query202_ndc_evidence_mode_preregistration(root: Path) -&gt; dict[str, Any]</code> |  |
| [L347](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L347) | function/method | <code>validate_query202_ndc_evidence_mode_preregistration(config: Mapping[str, Any]) -&gt; list[str]</code> |  |
| [L458](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L458) | function/method | <code>_implementation_bundle_snapshot(root: Path, paths: Sequence[str]) -&gt; tuple[str, dict[str, tuple[str, dict[str, Any]]]]</code> |  |
| [L478](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L478) | function/method | <code>implementation_bundle_sha256(root: Path, paths: Sequence[str]) -&gt; str</code> |  |
| [L483](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L483) | function/method | <code>_check_equal(checks: dict[str, bool], errors: list[str], label: str, actual: object, expected: object) -&gt; None</code> |  |
| [L496](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L496) | function/method | <code>_git_ignored(root: Path, relative: str) -&gt; bool</code> |  |
| [L509](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L509) | function/method | <code>_verify_source_evidence(root: Path, errors: list[str]) -&gt; tuple[dict[str, bool], dict[str, tuple[str, dict[str, Any]]], dict[str, Any] &#124; None]</code> |  |
| [L765](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L765) | function/method | <code>_verify_snapshot_closure(root: Path, initial_snapshots: Mapping[str, tuple[str, Mapping[str, Any]]], initial_artifact_directory: Mapping[str, Any] &#124; None, errors: list[str]) -&gt; dict[str, bool]</code> | Re-hash every dependency after all first-pass validation is complete. |
| [L802](../src/april_repro/query202_ndc_evidence_mode_preregistration.py#L802) | function/method | <code>query202_ndc_evidence_mode_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |

<a id="module-8ed920062a25"></a>

## src/april_repro/query202_pre_adjudication.py

[Open source](../src/april_repro/query202_pre_adjudication.py)

Source module docstring:

> Fail-closed runner for D005 Query-202 pre-adjudication evidence v2. The database phase executes nine complete typed-boundary statements followed by seven independently bounded physical statements for each of 64 subject buckets in one PostgreSQL REPEATABLE READ READ ONLY transaction. Database frames are held only in an anonymous mode-0600 spool until an explicit rollback and a clean psql exit have both been confirmed. Only then may exact private evidence be merged and persisted. This component extracts local evidence. It never decides product identity, maps a route, accepts a source policy, constructs an action/episode/label/cohort, or emits a patient, admission, event, order identifier, timestamp, raw local value, NDC, or per-value hash in public metadata.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L149](../src/april_repro/query202_pre_adjudication.py#L149) | class | <code>BoundarySpec()</code> |  |
| [L158](../src/april_repro/query202_pre_adjudication.py#L158) | class | <code>CrosswalkSpec()</code> |  |
| [L222](../src/april_repro/query202_pre_adjudication.py#L222) | function/method | <code>_now() -&gt; str</code> |  |
| [L226](../src/april_repro/query202_pre_adjudication.py#L226) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L230](../src/april_repro/query202_pre_adjudication.py#L230) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L234](../src/april_repro/query202_pre_adjudication.py#L234) | function/method | <code>_strict_uint(value: str, label: str, maximum: int=MAX_EXACT_COUNT) -&gt; int</code> |  |
| [L243](../src/april_repro/query202_pre_adjudication.py#L243) | function/method | <code>_snapshot_token(value: Any, label: str) -&gt; str</code> |  |
| [L256](../src/april_repro/query202_pre_adjudication.py#L256) | function/method | <code>_implementation_bundle(root: Path, paths: tuple[str, ...]) -&gt; dict[str, Any]</code> |  |
| [L285](../src/april_repro/query202_pre_adjudication.py#L285) | function/method | <code>implementation_bundles(root: Path) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L292](../src/april_repro/query202_pre_adjudication.py#L292) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L315](../src/april_repro/query202_pre_adjudication.py#L315) | function/method | <code>_remove_values(paths: Iterable[Path]) -&gt; bool</code> |  |
| [L325](../src/april_repro/query202_pre_adjudication.py#L325) | function/method | <code>_require_database_disk_headroom(directory: Path) -&gt; int</code> | Fail closed unless the artifact filesystem can hold one bounded phase. |
| [L350](../src/april_repro/query202_pre_adjudication.py#L350) | class | <code>_CompressedFrameIndex()</code> |  |
| [L357](../src/april_repro/query202_pre_adjudication.py#L357) | class | <code>_AnonymousFrameSpool()</code> | One unlinked mode-0600 file holding independent zlib frame members. |
| [L363](../src/april_repro/query202_pre_adjudication.py#L363) | function/method | <code>_AnonymousFrameSpool.__init__(self, directory: Path)</code> |  |
| [L375](../src/april_repro/query202_pre_adjudication.py#L375) | function/method | <code>_AnonymousFrameSpool.append(self, label: str, payload: bytes) -&gt; int</code> |  |
| [L395](../src/april_repro/query202_pre_adjudication.py#L395) | function/method | <code>_AnonymousFrameSpool.append.write_compressed(chunk: bytes) -&gt; None</code> |  |
| [L445](../src/april_repro/query202_pre_adjudication.py#L445) | function/method | <code>_AnonymousFrameSpool.read(self, label: str) -&gt; bytes</code> |  |
| [L489](../src/april_repro/query202_pre_adjudication.py#L489) | function/method | <code>_AnonymousFrameSpool.labels(self) -&gt; set[str]</code> |  |
| [L493](../src/april_repro/query202_pre_adjudication.py#L493) | function/method | <code>_AnonymousFrameSpool.closed(self) -&gt; bool</code> |  |
| [L496](../src/april_repro/query202_pre_adjudication.py#L496) | function/method | <code>_AnonymousFrameSpool.close(self) -&gt; None</code> |  |
| [L504](../src/april_repro/query202_pre_adjudication.py#L504) | class | <code>_CompressedRunIndex()</code> |  |
| [L512](../src/april_repro/query202_pre_adjudication.py#L512) | function/method | <code>_compact_json_line(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L527](../src/april_repro/query202_pre_adjudication.py#L527) | function/method | <code>_unique_json_object(payload: bytes, label: str) -&gt; dict[str, Any]</code> |  |
| [L528](../src/april_repro/query202_pre_adjudication.py#L528) | function/method | <code>_unique_json_object.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L547](../src/april_repro/query202_pre_adjudication.py#L547) | class | <code>_AnonymousSortedRunSpool()</code> | Anonymous compressed logical-bucket runs for bounded external merging. |
| [L556](../src/april_repro/query202_pre_adjudication.py#L556) | function/method | <code>_AnonymousSortedRunSpool.__init__(self, directory: Path)</code> |  |
| [L568](../src/april_repro/query202_pre_adjudication.py#L568) | function/method | <code>_AnonymousSortedRunSpool.append(self, label: str, records: Iterable[Mapping[str, Any]]) -&gt; int</code> |  |
| [L583](../src/april_repro/query202_pre_adjudication.py#L583) | function/method | <code>_AnonymousSortedRunSpool.append.write_compressed(chunk: bytes) -&gt; None</code> |  |
| [L665](../src/april_repro/query202_pre_adjudication.py#L665) | function/method | <code>_AnonymousSortedRunSpool.iter_records(self, label: str, spec: CrosswalkSpec) -&gt; Iterable[dict[str, Any]]</code> |  |
| [L684](../src/april_repro/query202_pre_adjudication.py#L684) | function/method | <code>_AnonymousSortedRunSpool.iter_records.consume(chunk: bytes) -&gt; Iterable[dict[str, Any]]</code> |  |
| [L788](../src/april_repro/query202_pre_adjudication.py#L788) | function/method | <code>_AnonymousSortedRunSpool.labels(self) -&gt; set[str]</code> |  |
| [L791](../src/april_repro/query202_pre_adjudication.py#L791) | function/method | <code>_AnonymousSortedRunSpool.stage_ledger(self) -&gt; dict[str, dict[str, int]]</code> | Return an aggregate that can be persisted without exposing values. |
| [L813](../src/april_repro/query202_pre_adjudication.py#L813) | function/method | <code>_AnonymousSortedRunSpool.closed(self) -&gt; bool</code> |  |
| [L816](../src/april_repro/query202_pre_adjudication.py#L816) | function/method | <code>_AnonymousSortedRunSpool.close(self) -&gt; None</code> |  |
| [L823](../src/april_repro/query202_pre_adjudication.py#L823) | class | <code>_BoundedStoredWriter()</code> |  |
| [L824](../src/april_repro/query202_pre_adjudication.py#L824) | function/method | <code>_BoundedStoredWriter.__init__(self, handle: Any, limit: int)</code> |  |
| [L830](../src/april_repro/query202_pre_adjudication.py#L830) | function/method | <code>_BoundedStoredWriter.write(self, payload: bytes) -&gt; int</code> |  |
| [L840](../src/april_repro/query202_pre_adjudication.py#L840) | function/method | <code>_BoundedStoredWriter.flush(self) -&gt; None</code> |  |
| [L843](../src/april_repro/query202_pre_adjudication.py#L843) | function/method | <code>_BoundedStoredWriter.tell(self) -&gt; int</code> |  |
| [L847](../src/april_repro/query202_pre_adjudication.py#L847) | class | <code>_GzipNdjsonWriter()</code> | Deterministic, bounded, mode-0600 gzip NDJSON artifact writer. |
| [L850](../src/april_repro/query202_pre_adjudication.py#L850) | function/method | <code>_GzipNdjsonWriter.__init__(self, path: Path)</code> |  |
| [L881](../src/april_repro/query202_pre_adjudication.py#L881) | function/method | <code>_GzipNdjsonWriter.write_record(self, value: Mapping[str, Any]) -&gt; None</code> |  |
| [L898](../src/april_repro/query202_pre_adjudication.py#L898) | function/method | <code>_GzipNdjsonWriter.finish(self) -&gt; dict[str, Any]</code> |  |
| [L924](../src/april_repro/query202_pre_adjudication.py#L924) | function/method | <code>_GzipNdjsonWriter.abort(self) -&gt; None</code> |  |
| [L947](../src/april_repro/query202_pre_adjudication.py#L947) | function/method | <code>typed_boundary_set_sha256(source_field: str, records: Iterable[Mapping[str, Any]]) -&gt; str</code> |  |
| [L983](../src/april_repro/query202_pre_adjudication.py#L983) | function/method | <code>nonnull_source_set_sha256(source_field: str, records: Iterable[Mapping[str, Any]]) -&gt; str</code> | Hash one exact non-NULL source-field set using the Q201 seed framing. |
| [L1007](../src/april_repro/query202_pre_adjudication.py#L1007) | function/method | <code>_semantic_seed_records(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; list[tuple[str, str]]</code> |  |
| [L1029](../src/april_repro/query202_pre_adjudication.py#L1029) | function/method | <code>semantic_seed_set_sha256(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[int, str]</code> |  |
| [L1046](../src/april_repro/query202_pre_adjudication.py#L1046) | function/method | <code>_decode_boundary_frame(frame: bytes, spec: BoundarySpec) -&gt; dict[str, Any]</code> |  |
| [L1149](../src/april_repro/query202_pre_adjudication.py#L1149) | function/method | <code>_canonical_tuple_object(value: Any) -&gt; tuple[dict[str, str &#124; None], bytes]</code> |  |
| [L1168](../src/april_repro/query202_pre_adjudication.py#L1168) | function/method | <code>encode_typed_tuple(stage: str, tuple_kind: str, value: Mapping[str, str &#124; None]) -&gt; bytes</code> |  |
| [L1193](../src/april_repro/query202_pre_adjudication.py#L1193) | function/method | <code>_decode_crosswalk_frame(frame: bytes, spec: BucketStatementSpec, bucket_index: int) -&gt; dict[str, Any]</code> |  |
| [L1321](../src/april_repro/query202_pre_adjudication.py#L1321) | function/method | <code>combine_crosswalk_statement_fragments(spec: CrosswalkSpec, bucket_index: int, fragments: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, Any]</code> | Reconstruct one old-shape logical bucket from its physical frames. |
| [L1375](../src/april_repro/query202_pre_adjudication.py#L1375) | function/method | <code>combine_crosswalk_statement_fragments.add_bounded(current: int, value: Any, label: str) -&gt; int</code> |  |
| [L1530](../src/april_repro/query202_pre_adjudication.py#L1530) | function/method | <code>_hash_merged_records(stage: str, records: list[Mapping[str, Any]]) -&gt; tuple[str, str]</code> |  |
| [L1554](../src/april_repro/query202_pre_adjudication.py#L1554) | function/method | <code>merge_crosswalk_fragments(spec: CrosswalkSpec, fragments: Mapping[int, Mapping[str, Any]] &#124; Iterable[tuple[int, Mapping[str, Any]]], *, expected_global_input_rows: int, bucket_count: int=BUCKET_COUNT) -&gt; dict[str, Any]</code> | Strictly merge exact tuples; bucket hashes are never concatenated. |
| [L1683](../src/april_repro/query202_pre_adjudication.py#L1683) | function/method | <code>_iter_merged_sorted_runs(spec: CrosswalkSpec, spool: _AnonymousSortedRunSpool) -&gt; Iterable[dict[str, Any]]</code> | Merge 64 strictly sorted bucket runs while retaining one row per run. |
| [L1701](../src/april_repro/query202_pre_adjudication.py#L1701) | function/method | <code>_iter_merged_sorted_runs.advance(index: int) -&gt; None</code> |  |
| [L1736](../src/april_repro/query202_pre_adjudication.py#L1736) | function/method | <code>_scan_external_crosswalk(spec: CrosswalkSpec, fragments: Mapping[int, Mapping[str, Any]], spool: _AnonymousSortedRunSpool, *, expected_global_input_rows: int) -&gt; dict[str, Any]</code> | First external-merge pass: verify controls and count merged rows. |
| [L1757](../src/april_repro/query202_pre_adjudication.py#L1757) | function/method | <code>_scan_external_crosswalk.add(current: int, value: Any, label: str) -&gt; int</code> |  |
| [L1851](../src/april_repro/query202_pre_adjudication.py#L1851) | function/method | <code>_new_tuple_hashers(stage: str, record_count: int) -&gt; tuple[Any, Any]</code> |  |
| [L1866](../src/april_repro/query202_pre_adjudication.py#L1866) | function/method | <code>_update_tuple_hashers(hashers: tuple[Any, Any], encoded: bytes, multiplicity: int) -&gt; None</code> |  |
| [L1877](../src/april_repro/query202_pre_adjudication.py#L1877) | function/method | <code>crosswalk_global_denominators_from_boundaries(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, int]</code> | Derive the two global base-row controls from the same-snapshot 202a scans. |
| [L1922](../src/april_repro/query202_pre_adjudication.py#L1922) | function/method | <code>crosswalk_physical_input_denominators_from_boundaries(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; dict[str, int]</code> | Return the separately conserved base-row total for every input owner. |
| [L1938](../src/april_repro/query202_pre_adjudication.py#L1938) | function/method | <code>_assert_one_snapshot(boundaries: Mapping[str, Mapping[str, Any]], crosswalks: Mapping[str, Mapping[str, Any]]) -&gt; str</code> |  |
| [L1953](../src/april_repro/query202_pre_adjudication.py#L1953) | function/method | <code>_validate_boundary_expectations(boundaries: Mapping[str, Mapping[str, Any]], report: Mapping[str, Any]) -&gt; None</code> |  |
| [L1979](../src/april_repro/query202_pre_adjudication.py#L1979) | function/method | <code>_load_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |
| [L1987](../src/april_repro/query202_pre_adjudication.py#L1987) | function/method | <code>_validate_preregistration_gate(report: Any) -&gt; dict[str, Any]</code> |  |
| [L2030](../src/april_repro/query202_pre_adjudication.py#L2030) | function/method | <code>_public_boundary_summary(source: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2045](../src/april_repro/query202_pre_adjudication.py#L2045) | function/method | <code>_private_stream_header(preregistered: Mapping[str, Any], snapshot_token: str) -&gt; dict[str, Any]</code> |  |
| [L2087](../src/april_repro/query202_pre_adjudication.py#L2087) | function/method | <code>_private_stream_view(header: Mapping[str, Any], boundaries: Mapping[str, Mapping[str, Any]], crosswalks: Mapping[str, Mapping[str, Any]], seed_count: int, seed_hash: str) -&gt; dict[str, Any]</code> |  |
| [L2151](../src/april_repro/query202_pre_adjudication.py#L2151) | function/method | <code>_write_private_ndjson(path: Path, boundaries: Mapping[str, Mapping[str, Any]], crosswalks: dict[str, dict[str, Any]], run_spool: _AnonymousSortedRunSpool, preregistered: Mapping[str, Any], snapshot_token: str) -&gt; tuple[dict[str, Any], dict[str, Any]]</code> | Write exact evidence without constructing a global Python payload. |
| [L2340](../src/april_repro/query202_pre_adjudication.py#L2340) | function/method | <code>build_aggregate_summary(private: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L2394](../src/april_repro/query202_pre_adjudication.py#L2394) | function/method | <code>_assert_value_free_public_payload(payload: Mapping[str, Any], forbidden_values: Iterable[str]) -&gt; None</code> |  |
| [L2413](../src/april_repro/query202_pre_adjudication.py#L2413) | function/method | <code>_assert_value_free_public_payload.walk(value: Any) -&gt; None</code> |  |
| [L2430](../src/april_repro/query202_pre_adjudication.py#L2430) | function/method | <code>_session_preamble() -&gt; str</code> |  |
| [L2445](../src/april_repro/query202_pre_adjudication.py#L2445) | function/method | <code>_stage_control(statement: str, marker: str, *, first: bool) -&gt; str</code> |  |
| [L2456](../src/april_repro/query202_pre_adjudication.py#L2456) | function/method | <code>_render_bucket_statement(template: str, bucket_index: int) -&gt; str</code> |  |
| [L2463](../src/april_repro/query202_pre_adjudication.py#L2463) | function/method | <code>_initial_stage(label: str, file: str, bucket_index: int &#124; None=None) -&gt; dict[str, Any]</code> |  |
| [L2475](../src/april_repro/query202_pre_adjudication.py#L2475) | function/method | <code>run_query202_pre_adjudication(root: Path) -&gt; dict[str, Any]</code> | Execute lifecycle A v2 and return terminal-safe metadata only. |

<a id="module-7a611285d725"></a>

## src/april_repro/query202_pre_adjudication_audit.py

[Open source](../src/april_repro/query202_pre_adjudication_audit.py)

Source module docstring:

> Independent offline audit for Query-202 pre-adjudication lifecycle A v2. This module intentionally imports neither the database runner nor any of its hashing, tuple, SQL-rendering, or preregistration helpers. It reimplements the byte contracts and validates saved artifacts without opening a database connection. Audit failures expose only fixed check names, never local values.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L423](../src/april_repro/query202_pre_adjudication_audit.py#L423) | function/method | <code>_physical_control_names(spec: Mapping[str, Any]) -&gt; tuple[str, ...]</code> | Independent exact control inventory for one physical bucket statement. |
| [L505](../src/april_repro/query202_pre_adjudication_audit.py#L505) | class | <code>AuditContractError(RuntimeError)</code> | A value-safe audit failure identified only by a fixed check name. |
| [L509](../src/april_repro/query202_pre_adjudication_audit.py#L509) | class | <code>Checks()</code> |  |
| [L510](../src/april_repro/query202_pre_adjudication_audit.py#L510) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L515](../src/april_repro/query202_pre_adjudication_audit.py#L515) | function/method | <code>Checks.require(self, condition: bool, name: str) -&gt; None</code> |  |
| [L523](../src/april_repro/query202_pre_adjudication_audit.py#L523) | function/method | <code>Checks.check(self, condition: bool, name: str) -&gt; None</code> |  |
| [L530](../src/april_repro/query202_pre_adjudication_audit.py#L530) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L534](../src/april_repro/query202_pre_adjudication_audit.py#L534) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L542](../src/april_repro/query202_pre_adjudication_audit.py#L542) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L546](../src/april_repro/query202_pre_adjudication_audit.py#L546) | function/method | <code>_read_json(path: Path, limit: int, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L554](../src/april_repro/query202_pre_adjudication_audit.py#L554) | function/method | <code>_read_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L562](../src/april_repro/query202_pre_adjudication_audit.py#L562) | function/method | <code>_read_json.invalid_constant(_: str) -&gt; Any</code> |  |
| [L580](../src/april_repro/query202_pre_adjudication_audit.py#L580) | function/method | <code>_safe_filename(directory: Path, value: Any, label: str) -&gt; Path</code> |  |
| [L589](../src/april_repro/query202_pre_adjudication_audit.py#L589) | function/method | <code>_safe_relative(value: Any) -&gt; bool</code> |  |
| [L596](../src/april_repro/query202_pre_adjudication_audit.py#L596) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L608](../src/april_repro/query202_pre_adjudication_audit.py#L608) | function/method | <code>_bundle(root: Path, paths: tuple[str, ...]) -&gt; dict[str, Any]</code> |  |
| [L636](../src/april_repro/query202_pre_adjudication_audit.py#L636) | function/method | <code>implementation_bundles(root: Path) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L640](../src/april_repro/query202_pre_adjudication_audit.py#L640) | function/method | <code>_finite_nonnegative(value: Any, maximum: float &#124; None=None) -&gt; bool</code> |  |
| [L649](../src/april_repro/query202_pre_adjudication_audit.py#L649) | function/method | <code>_parse_utc(value: Any) -&gt; datetime &#124; None</code> |  |
| [L661](../src/april_repro/query202_pre_adjudication_audit.py#L661) | function/method | <code>_utc_attestation_interval(value: Mapping[str, Any]) -&gt; bool</code> |  |
| [L676](../src/april_repro/query202_pre_adjudication_audit.py#L676) | function/method | <code>_expected_explain_metadata(root: Path) -&gt; tuple[list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L715](../src/april_repro/query202_pre_adjudication_audit.py#L715) | function/method | <code>_typed_hash(field: str, records: list[Mapping[str, Any]]) -&gt; str</code> |  |
| [L744](../src/april_repro/query202_pre_adjudication_audit.py#L744) | function/method | <code>_nonnull_hash(field: str, records: list[Mapping[str, Any]]) -&gt; str</code> |  |
| [L763](../src/april_repro/query202_pre_adjudication_audit.py#L763) | function/method | <code>_seed_records(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; list[dict[str, str]]</code> |  |
| [L783](../src/april_repro/query202_pre_adjudication_audit.py#L783) | function/method | <code>_seed_hash(boundaries: Mapping[str, Mapping[str, Any]]) -&gt; tuple[int, str]</code> |  |
| [L797](../src/april_repro/query202_pre_adjudication_audit.py#L797) | function/method | <code>_encode_tuple(stage: str, kind: str, value: Mapping[str, str &#124; None]) -&gt; bytes</code> |  |
| [L821](../src/april_repro/query202_pre_adjudication_audit.py#L821) | function/method | <code>_tuple_hashes(stage: str, records: list[Mapping[str, Any]]) -&gt; tuple[str, str]</code> |  |
| [L839](../src/april_repro/query202_pre_adjudication_audit.py#L839) | function/method | <code>_public_strings(value: Any) -&gt; set[str]</code> |  |
| [L853](../src/april_repro/query202_pre_adjudication_audit.py#L853) | class | <code>_PrivateNdjsonReader()</code> | One-pass, independently bounded gzip/NDJSON reader. |
| [L858](../src/april_repro/query202_pre_adjudication_audit.py#L858) | function/method | <code>_PrivateNdjsonReader.__init__(self, path: Path)</code> |  |
| [L872](../src/april_repro/query202_pre_adjudication_audit.py#L872) | function/method | <code>_PrivateNdjsonReader._decode_record(line: bytes) -&gt; dict[str, Any]</code> |  |
| [L873](../src/april_repro/query202_pre_adjudication_audit.py#L873) | function/method | <code>_PrivateNdjsonReader._decode_record.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L881](../src/april_repro/query202_pre_adjudication_audit.py#L881) | function/method | <code>_PrivateNdjsonReader._decode_record.invalid_constant(_: str) -&gt; Any</code> |  |
| [L898](../src/april_repro/query202_pre_adjudication_audit.py#L898) | function/method | <code>_PrivateNdjsonReader.__iter__(self) -&gt; Iterator[dict[str, Any]]</code> |  |
| [L906](../src/april_repro/query202_pre_adjudication_audit.py#L906) | function/method | <code>_PrivateNdjsonReader.__iter__.consume(chunk: bytes) -&gt; list[dict[str, Any]]</code> |  |
| [L981](../src/april_repro/query202_pre_adjudication_audit.py#L981) | class | <code>_PrivateRecordCursor()</code> |  |
| [L982](../src/april_repro/query202_pre_adjudication_audit.py#L982) | function/method | <code>_PrivateRecordCursor.__init__(self, reader: _PrivateNdjsonReader)</code> |  |
| [L986](../src/april_repro/query202_pre_adjudication_audit.py#L986) | function/method | <code>_PrivateRecordCursor.take(self, record_type: str) -&gt; dict[str, Any]</code> |  |
| [L995](../src/april_repro/query202_pre_adjudication_audit.py#L995) | function/method | <code>_PrivateRecordCursor.finish(self) -&gt; None</code> |  |
| [L1003](../src/april_repro/query202_pre_adjudication_audit.py#L1003) | function/method | <code>_exact_record_keys(value: Any, expected: set[str], label: str) -&gt; dict[str, Any]</code> |  |
| [L1011](../src/april_repro/query202_pre_adjudication_audit.py#L1011) | function/method | <code>_strict_json_equal(observed: Any, expected: Any) -&gt; bool</code> | JSON equality that does not equate booleans with integers. |
| [L1028](../src/april_repro/query202_pre_adjudication_audit.py#L1028) | function/method | <code>_new_stream_tuple_hashers(stage: str, count: int) -&gt; tuple[Any, Any]</code> |  |
| [L1039](../src/april_repro/query202_pre_adjudication_audit.py#L1039) | function/method | <code>_update_stream_tuple_hashers(hashers: tuple[Any, Any], encoded: bytes, multiplicity: int) -&gt; None</code> |  |
| [L1050](../src/april_repro/query202_pre_adjudication_audit.py#L1050) | function/method | <code>_stream_private_artifact(path: Path, entry: Mapping[str, Any], public_strings: set[str], checks: Checks) -&gt; dict[str, Any]</code> | Validate the complete private record protocol with bounded memory. |
| [L1594](../src/april_repro/query202_pre_adjudication_audit.py#L1594) | function/method | <code>_check_public_keys(value: Any, checks: Checks, label: str) -&gt; None</code> |  |
| [L1610](../src/april_repro/query202_pre_adjudication_audit.py#L1610) | function/method | <code>_contract_projection(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1629](../src/april_repro/query202_pre_adjudication_audit.py#L1629) | function/method | <code>_contract_hash(config: Mapping[str, Any]) -&gt; str</code> |  |
| [L1636](../src/april_repro/query202_pre_adjudication_audit.py#L1636) | function/method | <code>_validate_config(root: Path, config: Mapping[str, Any], bundles: Mapping[str, Mapping[str, Any]], checks: Checks) -&gt; None</code> |  |
| [L2097](../src/april_repro/query202_pre_adjudication_audit.py#L2097) | function/method | <code>_validate_boundaries(boundaries: Any, checks: Checks) -&gt; tuple[dict[str, dict[str, Any]], set[str], dict[str, Any]]</code> |  |
| [L2198](../src/april_repro/query202_pre_adjudication_audit.py#L2198) | function/method | <code>_validate_crosswalks(crosswalks: Any, boundaries: Mapping[str, Mapping[str, Any]], checks: Checks) -&gt; tuple[dict[str, dict[str, Any]], set[str]]</code> |  |
| [L2380](../src/april_repro/query202_pre_adjudication_audit.py#L2380) | function/method | <code>_statement_body(sql: str) -&gt; str</code> | Independently remove the sole terminal semicolon from reviewed SQL. |
| [L2388](../src/april_repro/query202_pre_adjudication_audit.py#L2388) | function/method | <code>_template_control_names(sql: str) -&gt; tuple[str, ...]</code> | Extract only literal control names from the frozen controls CTE. |
| [L2401](../src/april_repro/query202_pre_adjudication_audit.py#L2401) | function/method | <code>_validate_executed_sql(root: Path, payload: bytes, checks: Checks) -&gt; list[bytes]</code> |  |
| [L2482](../src/april_repro/query202_pre_adjudication_audit.py#L2482) | function/method | <code>_validate_manifest_stages(root: Path, manifest: Mapping[str, Any], entry: Mapping[str, Any], private: Mapping[str, Any], executed_controls: list[bytes], checks: Checks) -&gt; None</code> |  |
| [L2745](../src/april_repro/query202_pre_adjudication_audit.py#L2745) | function/method | <code>_validate_git_ignore(root: Path, directory: Path, checks: Checks) -&gt; None</code> |  |
| [L2757](../src/april_repro/query202_pre_adjudication_audit.py#L2757) | function/method | <code>_audit_complete_artifact(root: Path, directory: Path, checks: Checks) -&gt; dict[str, Any]</code> |  |
| [L3297](../src/april_repro/query202_pre_adjudication_audit.py#L3297) | function/method | <code>audit_query202_pre_adjudication(root: Path, artifact_directory: Path) -&gt; dict[str, Any]</code> | Audit one completed artifact and persist a value-safe audit summary. |

<a id="module-570ac2027d54"></a>

## src/april_repro/query202_pre_adjudication_preregistration_v2.py

[Open source](../src/april_repro/query202_pre_adjudication_preregistration_v2.py)

Source module docstring:

> Validation and freeze gates for Query 202 lifecycle A v2. The v1 file remains an immutable architecture record. This module validates the separately versioned, implementable v2 contract. It supports exactly two states: a fail-closed implementation draft and a fully pinned execution freeze. Changing the root status or permission flag cannot satisfy the freeze gate.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L373](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L373) | function/method | <code>_sha_bytes(payload: bytes) -&gt; str</code> |  |
| [L377](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L377) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L385](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L385) | function/method | <code>_safe_relative(value: Any) -&gt; bool</code> |  |
| [L392](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L392) | function/method | <code>read_potassium_query202_pre_adjudication_v2_preregistration(root: Path) -&gt; dict[str, Any]</code> |  |
| [L399](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L399) | function/method | <code>_bundle(root: Path, paths: list[str]) -&gt; dict[str, Any]</code> |  |
| [L433](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L433) | function/method | <code>implementation_bundles(root: Path, config: Mapping[str, Any] &#124; None=None) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L448](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L448) | function/method | <code>_contract_projection(config: Mapping[str, Any]) -&gt; dict[str, Any]</code> | Return the scientific/engineering contract covered by fixture attestation. |
| [L485](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L485) | function/method | <code>scientific_contract_sha256(config: Mapping[str, Any]) -&gt; str</code> |  |
| [L495](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L495) | function/method | <code>_expect(table: Mapping[str, Any], key: str, expected: Any, label: str, errors: list[str]) -&gt; None</code> |  |
| [L502](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L502) | function/method | <code>_validate_guards(config: Mapping[str, Any], frozen: bool, errors: list[str]) -&gt; None</code> |  |
| [L514](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L514) | function/method | <code>_validate_state(config: Mapping[str, Any], errors: list[str]) -&gt; bool</code> |  |
| [L536](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L536) | function/method | <code>_validate_contract(config: Mapping[str, Any], errors: list[str]) -&gt; None</code> |  |
| [L891](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L891) | function/method | <code>_validate_implementation(config: Mapping[str, Any], frozen: bool, errors: list[str]) -&gt; None</code> |  |
| [L919](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L919) | function/method | <code>_validate_fixture_gate(config: Mapping[str, Any], frozen: bool, errors: list[str]) -&gt; None</code> |  |
| [L970](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L970) | function/method | <code>validate_potassium_query202_pre_adjudication_v2_preregistration(config: Mapping[str, Any]) -&gt; list[str]</code> |  |
| [L997](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L997) | function/method | <code>_verify_evidence(root: Path, config: Mapping[str, Any], errors: list[str]) -&gt; int</code> |  |
| [L1012](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1012) | function/method | <code>_read_unique_json(path: Path) -&gt; dict[str, Any]</code> |  |
| [L1013](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1013) | function/method | <code>_read_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L1027](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1027) | function/method | <code>_nonnull_set_hash(source_field: str, values: list[str]) -&gt; str</code> |  |
| [L1042](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1042) | function/method | <code>_typed_set_hash(source_field: str, records: list[Mapping[str, Any]]) -&gt; str</code> |  |
| [L1073](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1073) | function/method | <code>_semantic_seed_hash(items: list[tuple[str, str]]) -&gt; str</code> |  |
| [L1087](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1087) | function/method | <code>_verify_boundary_lineage(root: Path) -&gt; tuple[bool, str &#124; None]</code> | Independently rebuild all nine frozen nonnull boundaries from evidence. |
| [L1161](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1161) | function/method | <code>_verify_attestation(root: Path, config: Mapping[str, Any], bundles: Mapping[str, Mapping[str, Any]]) -&gt; tuple[bool, list[str]]</code> |  |
| [L1233](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1233) | function/method | <code>_finite_nonnegative(value: Any, maximum: float &#124; None=None) -&gt; bool</code> |  |
| [L1242](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1242) | function/method | <code>_utc_attestation_interval(value: Mapping[str, Any]) -&gt; bool</code> |  |
| [L1257](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1257) | function/method | <code>_expected_explain_statements(root: Path) -&gt; tuple[list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L1291](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1291) | function/method | <code>_verify_readonly_explain_attestation(root: Path, config: Mapping[str, Any], bundles: Mapping[str, Mapping[str, Any]]) -&gt; tuple[bool, list[str]]</code> | Verify the separate real-PostgreSQL EXPLAIN-only execution gate. |
| [L1401](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1401) | function/method | <code>potassium_query202_pre_adjudication_v2_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |
| [L1520](../src/april_repro/query202_pre_adjudication_preregistration_v2.py#L1520) | function/method | <code>build_fixture_attestation(root: Path, *, tests_run: int, test_command: str) -&gt; dict[str, Any]</code> | Build the deterministic content that a successful fixture run may sign. |

<a id="module-4809a5f369fb"></a>

## src/april_repro/query202_preadjudication_sql_v2.py

[Open source](../src/april_repro/query202_preadjudication_sql_v2.py)

Source module docstring:

> Pure SQL/render/merge contract for Query 202 pre-adjudication v2. This module does not connect to PostgreSQL. It freezes the closed SQL file inventory, the lifecycle-A subject partition, and the private tuple schemas so the runner and independent auditor can reject drift before any MIMIC query.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L54](../src/april_repro/query202_preadjudication_sql_v2.py#L54) | class | <code>BoundaryStage()</code> |  |
| [L63](../src/april_repro/query202_preadjudication_sql_v2.py#L63) | class | <code>BucketStatementSpec()</code> | One independently bounded physical statement of a logical bucket stage. |
| [L410](../src/april_repro/query202_preadjudication_sql_v2.py#L410) | function/method | <code>_control_names(stage: str) -&gt; tuple[str, ...]</code> |  |
| [L428](../src/april_repro/query202_preadjudication_sql_v2.py#L428) | function/method | <code>_physical_control_names(spec: BucketStatementSpec) -&gt; tuple[str, ...]</code> |  |
| [L452](../src/april_repro/query202_preadjudication_sql_v2.py#L452) | function/method | <code>subject_bucket(subject_id: int &#124; None) -&gt; int</code> | Return the lifecycle-A v2 bucket without importing lifecycle B. |
| [L464](../src/april_repro/query202_preadjudication_sql_v2.py#L464) | function/method | <code>validate_bucket_indices(indices: Sequence[int]) -&gt; None</code> |  |
| [L469](../src/april_repro/query202_preadjudication_sql_v2.py#L469) | function/method | <code>render_bucket_sql(template: str, bucket_index: int) -&gt; str</code> | Render the only permitted SQL marker after closed-range validation. |
| [L483](../src/april_repro/query202_preadjudication_sql_v2.py#L483) | function/method | <code>read_and_render_bucket_sql(root: Path, stage: str, bucket_index: int) -&gt; str</code> | Read and render one frozen physical bucket statement. |
| [L492](../src/april_repro/query202_preadjudication_sql_v2.py#L492) | function/method | <code>decode_and_validate_tuple_payload(stage: str, kind: str, value: str) -&gt; dict[str, str &#124; None]</code> | Decode one private tuple and require the exact frozen null/string schema. |
| [L498](../src/april_repro/query202_preadjudication_sql_v2.py#L498) | function/method | <code>decode_and_validate_tuple_payload.exact_object(pairs: list[tuple[str, object]]) -&gt; dict[str, object]</code> |  |
| [L521](../src/april_repro/query202_preadjudication_sql_v2.py#L521) | function/method | <code>merge_tuple_partitions(stage: str, partitions: Mapping[int, Iterable[tuple[str, bytes, int]]]) -&gt; list[tuple[str, bytes, int]]</code> | Reference merge: sum equal private tuples, then globally byte-sort. |

<a id="module-7752fb27fa99"></a>

## src/april_repro/query202_preregistration.py

[Open source](../src/april_repro/query202_preregistration.py)

Source module docstring:

> Machine validation for the split D005 Query 202 lifecycles. The original all-in-one architecture is retained only as a superseded record. Neither replacement component is executable: this module validates architecture and existing evidence, never promotes placeholders into an execution gate.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L55](../src/april_repro/query202_preregistration.py#L55) | function/method | <code>_sha256(path: Path) -&gt; str</code> |  |
| [L59](../src/april_repro/query202_preregistration.py#L59) | function/method | <code>_canonical_sha256(config: dict) -&gt; str</code> |  |
| [L66](../src/april_repro/query202_preregistration.py#L66) | function/method | <code>_read(root: Path, relative: Path) -&gt; dict</code> |  |
| [L71](../src/april_repro/query202_preregistration.py#L71) | function/method | <code>read_potassium_query202_extraction_preregistration(root: Path) -&gt; dict</code> | Read the superseded single-lifecycle record. |
| [L76](../src/april_repro/query202_preregistration.py#L76) | function/method | <code>read_potassium_query202_pre_adjudication_preregistration(root: Path) -&gt; dict</code> |  |
| [L80](../src/april_repro/query202_preregistration.py#L80) | function/method | <code>read_potassium_query202_mapped_event_application_preregistration(root: Path) -&gt; dict</code> |  |
| [L86](../src/april_repro/query202_preregistration.py#L86) | function/method | <code>_validate_false_guards(config: dict, errors: list[str]) -&gt; None</code> |  |
| [L96](../src/april_repro/query202_preregistration.py#L96) | function/method | <code>_validate_safe_evidence(config: dict, errors: list[str]) -&gt; None</code> |  |
| [L118](../src/april_repro/query202_preregistration.py#L118) | function/method | <code>_validate_transaction(transaction: object, snapshot_key: str, timeout_scope_key: str, errors: list[str]) -&gt; None</code> |  |
| [L150](../src/april_repro/query202_preregistration.py#L150) | function/method | <code>_validate_architecture_root(config: dict, component_id: str, rule_version: str, errors: list[str]) -&gt; None</code> |  |
| [L172](../src/april_repro/query202_preregistration.py#L172) | function/method | <code>_validate_bucket_plan(config: dict, expected_stages: list[str], errors: list[str]) -&gt; None</code> |  |
| [L189](../src/april_repro/query202_preregistration.py#L189) | function/method | <code>_validate_architecture_only_implementation(config: dict, errors: list[str]) -&gt; None</code> |  |
| [L213](../src/april_repro/query202_preregistration.py#L213) | function/method | <code>validate_potassium_query202_extraction_preregistration(config: dict) -&gt; list[str]</code> | Validate that the old component is inert and explicitly superseded. |
| [L241](../src/april_repro/query202_preregistration.py#L241) | function/method | <code>validate_potassium_query202_pre_adjudication_preregistration(config: dict) -&gt; list[str]</code> | Validate lifecycle A without treating it as implemented or executable. |
| [L385](../src/april_repro/query202_preregistration.py#L385) | function/method | <code>validate_potassium_query202_mapped_event_application_preregistration(config: dict) -&gt; list[str]</code> | Validate lifecycle B while all frozen-input and implementation gates are shut. |
| [L477](../src/april_repro/query202_preregistration.py#L477) | function/method | <code>_check_evidence_files(root: Path, config: dict, errors: list[str]) -&gt; int</code> |  |
| [L495](../src/april_repro/query202_preregistration.py#L495) | function/method | <code>_verify_route_preflight_summary(root: Path, config: dict) -&gt; bool</code> |  |
| [L532](../src/april_repro/query202_preregistration.py#L532) | function/method | <code>_verify_pre_adjudication_seed_references(root: Path, config: dict) -&gt; bool</code> |  |
| [L595](../src/april_repro/query202_preregistration.py#L595) | function/method | <code>potassium_query202_extraction_preregistration_report(root: Path) -&gt; dict</code> | Report the old component only as an inert superseded record. |
| [L615](../src/april_repro/query202_preregistration.py#L615) | function/method | <code>potassium_query202_pre_adjudication_preregistration_report(root: Path) -&gt; dict</code> |  |
| [L658](../src/april_repro/query202_preregistration.py#L658) | function/method | <code>potassium_query202_mapped_event_application_preregistration_report(root: Path) -&gt; dict</code> |  |

<a id="module-4dc43ccab11c"></a>

## src/april_repro/query202_readonly_explain_attestation.py

[Open source](../src/april_repro/query202_readonly_explain_attestation.py)

Source module docstring:

> Real-PostgreSQL, EXPLAIN-only attestation for Query-202 lifecycle A v2. The attester opens one psql process and one REPEATABLE READ READ ONLY transaction. It asks PostgreSQL to plan the nine boundary statements plus bucket zero of each of the seven physical crosswalk statements. &#96;&#96;EXPLAIN&#96;&#96; query output is directed to the operating-system null device by psql, so plans never enter Python, stdout, stderr, or a persisted file. Only control markers use stdout. No artifact is created until an explicit rollback has been observed and psql has exited with status zero. The resulting JSON contains template and whole rendered-statement hashes, timings, and control claims; it contains no SQL, plan, database value, identifier, relation detail, or column detail.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L65](../src/april_repro/query202_readonly_explain_attestation.py#L65) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L69](../src/april_repro/query202_readonly_explain_attestation.py#L69) | function/method | <code>_now() -&gt; str</code> |  |
| [L73](../src/april_repro/query202_readonly_explain_attestation.py#L73) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L77](../src/april_repro/query202_readonly_explain_attestation.py#L77) | function/method | <code>_safe_relative(relative: str) -&gt; Path</code> |  |
| [L89](../src/april_repro/query202_readonly_explain_attestation.py#L89) | function/method | <code>_bundle(root: Path, paths: tuple[str, ...]) -&gt; dict[str, Any]</code> | Hash a closed file bundle with the Query-202 v2 framing contract. |
| [L120](../src/april_repro/query202_readonly_explain_attestation.py#L120) | function/method | <code>_load_execution_contract(root: Path) -&gt; dict[str, Any]</code> | Load, validate, and hash exactly the sixteen preregistered templates. |
| [L158](../src/april_repro/query202_readonly_explain_attestation.py#L158) | function/method | <code>_contract_fingerprint(contract: Mapping[str, Any]) -&gt; tuple[Any, ...]</code> |  |
| [L173](../src/april_repro/query202_readonly_explain_attestation.py#L173) | class | <code>_DiscardingExplainPsql(_PersistentPsql)</code> | Persistent psql whose query output and stderr cannot become files. |
| [L176](../src/april_repro/query202_readonly_explain_attestation.py#L176) | function/method | <code>_DiscardingExplainPsql.__init__(self, client: PsqlClient)</code> |  |
| [L208](../src/april_repro/query202_readonly_explain_attestation.py#L208) | function/method | <code>_DiscardingExplainPsql.close(self) -&gt; int</code> | Close psql, reducing anonymous stderr before unlink-on-close. |
| [L244](../src/april_repro/query202_readonly_explain_attestation.py#L244) | function/method | <code>_database_control(marker: str) -&gt; str</code> | Open the transaction and make PostgreSQL prove all three controls. |
| [L274](../src/april_repro/query202_readonly_explain_attestation.py#L274) | function/method | <code>_static_explain_control(statement: str) -&gt; str</code> | Return the independently reproducible part of one EXPLAIN control. |
| [L284](../src/april_repro/query202_readonly_explain_attestation.py#L284) | function/method | <code>_statement_control(statement: str, marker: str) -&gt; str</code> |  |
| [L293](../src/april_repro/query202_readonly_explain_attestation.py#L293) | function/method | <code>_update_transcript(digest: Any, control: str) -&gt; None</code> |  |
| [L299](../src/april_repro/query202_readonly_explain_attestation.py#L299) | function/method | <code>_git_ignored(root: Path, path: Path) -&gt; bool</code> |  |
| [L326](../src/april_repro/query202_readonly_explain_attestation.py#L326) | function/method | <code>_atomic_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L356](../src/april_repro/query202_readonly_explain_attestation.py#L356) | function/method | <code>_persist_attestation(root: Path, relative: Path, payload: bytes) -&gt; Path</code> |  |
| [L398](../src/april_repro/query202_readonly_explain_attestation.py#L398) | function/method | <code>_terminal_result(root: Path, path: Path, payload: bytes, attestation: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L415](../src/april_repro/query202_readonly_explain_attestation.py#L415) | function/method | <code>run_query202_readonly_explain_attestation(root: Path) -&gt; dict[str, Any]</code> | Execute the sixteen EXPLAIN-only checks and persist a success attestation. |

<a id="module-563e83980328"></a>

## src/april_repro/rewards.py

[Open source](../src/april_repro/rewards.py)

Source module docstring:

> Lab rewards and evaluation categories transcribed from APRIL. Source: Mandyam et al., APRIL, main-text Section 3.1 (PDF p. 4) and Appendix A / Figure 4 (PDF p. 17). The printed formula uses sigma=2.5 for both tasks. The plotted potassium curve appears inconsistent with that scale; this module follows the printed formula, not the plot. The F1 categories differ from the reward reference ranges. All lab values and reference boundaries are in mEq/L.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L26](../src/april_repro/rewards.py#L26) | function/method | <code>_finite_real(value: Real, name: str) -&gt; float</code> |  |
| [L38](../src/april_repro/rewards.py#L38) | function/method | <code>_validate_task(task: Task) -&gt; None</code> |  |
| [L43](../src/april_repro/rewards.py#L43) | function/method | <code>reward_from_lab(value: Real, task: Task, *, sigma: Real=PAPER_REWARD_SIGMA) -&gt; float</code> | Return the bounded reward from the paper's piecewise formula. |
| [L67](../src/april_repro/rewards.py#L67) | function/method | <code>bin_lab_value(value: Real, task: Task) -&gt; int</code> | Return the zero-based Appendix A F1 class; thresholds go right. |

<a id="module-2928af8fe7fc"></a>

## src/april_repro/route_adjudication.py

[Open source](../src/april_repro/route_adjudication.py)

Source module docstring:

> Private exact-value route review and source-specific mapping compilation. This module never connects to a database and never classifies route text. It builds a private human-review template from the audited mapping-preflight raw artifact, then expands reviewed canonical exact values back to source-specific keys. Unreviewed values remain &#96;&#96;unknown&#96;&#96; and no output unlocks Query 202.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L82](../src/april_repro/route_adjudication.py#L82) | class | <code>RouteAdjudicationError(RuntimeError)</code> | A fail-closed structural, lineage, privacy, or review error. |
| [L86](../src/april_repro/route_adjudication.py#L86) | function/method | <code>_now() -&gt; str</code> |  |
| [L90](../src/april_repro/route_adjudication.py#L90) | function/method | <code>_stamp() -&gt; str</code> |  |
| [L94](../src/april_repro/route_adjudication.py#L94) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L98](../src/april_repro/route_adjudication.py#L98) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L106](../src/april_repro/route_adjudication.py#L106) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L110](../src/april_repro/route_adjudication.py#L110) | function/method | <code>_read_unique_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L117](../src/april_repro/route_adjudication.py#L117) | function/method | <code>_read_unique_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L136](../src/april_repro/route_adjudication.py#L136) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L159](../src/april_repro/route_adjudication.py#L159) | function/method | <code>_json_bytes(value: Mapping[str, Any]) -&gt; bytes</code> |  |
| [L165](../src/april_repro/route_adjudication.py#L165) | function/method | <code>_bundle(root: Path, paths: Sequence[str]) -&gt; dict[str, Any]</code> |  |
| [L196](../src/april_repro/route_adjudication.py#L196) | function/method | <code>implementation_bundles(root: Path) -&gt; dict[str, dict[str, Any]]</code> |  |
| [L203](../src/april_repro/route_adjudication.py#L203) | function/method | <code>_safe_relative(root: Path, relative_text: Any, label: str) -&gt; Path</code> |  |
| [L217](../src/april_repro/route_adjudication.py#L217) | function/method | <code>_load_config(root: Path, *, require_frozen_hashes: bool=True) -&gt; dict[str, Any]</code> |  |
| [L316](../src/april_repro/route_adjudication.py#L316) | function/method | <code>_typed_set_sha256(source_field: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L367](../src/april_repro/route_adjudication.py#L367) | function/method | <code>_canonical_set_sha256(raw_values: Sequence[str]) -&gt; str</code> |  |
| [L380](../src/april_repro/route_adjudication.py#L380) | function/method | <code>_mapping_sha256(private_input_sha256: str, entries: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L384](../src/april_repro/route_adjudication.py#L384) | function/method | <code>_mapping_sha256.key(entry: Mapping[str, Any]) -&gt; tuple[bytes, int, bytes]</code> |  |
| [L422](../src/april_repro/route_adjudication.py#L422) | function/method | <code>_validate_preflight(root: Path, config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L529](../src/april_repro/route_adjudication.py#L529) | function/method | <code>_lineage(root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L549](../src/april_repro/route_adjudication.py#L549) | function/method | <code>_destination(root: Path, family: str) -&gt; Path</code> |  |
| [L559](../src/april_repro/route_adjudication.py#L559) | function/method | <code>_review_template(root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L654](../src/april_repro/route_adjudication.py#L654) | function/method | <code>_summary_from_review(review: Mapping[str, Any], review_sha256: str) -&gt; dict[str, Any]</code> |  |
| [L683](../src/april_repro/route_adjudication.py#L683) | function/method | <code>create_review_template(root: Path) -&gt; dict[str, Any]</code> | Create one private all-unknown review template from the frozen preflight. |
| [L749](../src/april_repro/route_adjudication.py#L749) | function/method | <code>_expected_review(root: Path, config_report: Mapping[str, Any], preflight: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L755](../src/april_repro/route_adjudication.py#L755) | function/method | <code>_validate_review(review: Mapping[str, Any], expected: Mapping[str, Any]) -&gt; tuple[list[dict[str, Any]], dict[str, int]]</code> |  |
| [L895](../src/april_repro/route_adjudication.py#L895) | function/method | <code>_mapping_summary(mapping: Mapping[str, Any], mapping_bytes: bytes) -&gt; dict[str, Any]</code> |  |
| [L953](../src/april_repro/route_adjudication.py#L953) | function/method | <code>compile_review(root: Path, review_path: Path) -&gt; dict[str, Any]</code> | Validate a private human review and compile all source-specific keys. |

<a id="module-fa9118784b62"></a>

## src/april_repro/route_adjudication_audit.py

[Open source](../src/april_repro/route_adjudication_audit.py)

Source module docstring:

> Independent offline audit for a compiled exact-value route mapping. The auditor intentionally does not import the generator/compiler module. It rebuilds the three route sets, the canonical exact bridge, source-specific mapping decisions, byte hashes, aggregate summaries, privacy checks, and modes from the saved private artifacts. It never opens a database or prints a raw route value.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L100](../src/april_repro/route_adjudication_audit.py#L100) | class | <code>AuditError(RuntimeError)</code> |  |
| [L104](../src/april_repro/route_adjudication_audit.py#L104) | class | <code>Checks()</code> |  |
| [L105](../src/april_repro/route_adjudication_audit.py#L105) | function/method | <code>Checks.__init__(self) -&gt; None</code> |  |
| [L110](../src/april_repro/route_adjudication_audit.py#L110) | function/method | <code>Checks.check(self, category: str, name: str, condition: bool) -&gt; None</code> |  |
| [L117](../src/april_repro/route_adjudication_audit.py#L117) | function/method | <code>_sha(payload: bytes) -&gt; str</code> |  |
| [L121](../src/april_repro/route_adjudication_audit.py#L121) | function/method | <code>_sha_file(path: Path) -&gt; str</code> |  |
| [L129](../src/april_repro/route_adjudication_audit.py#L129) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L133](../src/april_repro/route_adjudication_audit.py#L133) | function/method | <code>_read_json(path: Path, label: str) -&gt; tuple[dict[str, Any], bytes]</code> |  |
| [L138](../src/april_repro/route_adjudication_audit.py#L138) | function/method | <code>_read_json.unique(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L157](../src/april_repro/route_adjudication_audit.py#L157) | function/method | <code>_write_private(path: Path, payload: bytes) -&gt; None</code> |  |
| [L174](../src/april_repro/route_adjudication_audit.py#L174) | function/method | <code>_replace_private(path: Path, payload: bytes) -&gt; None</code> | Atomically persist a deterministic re-audit without following symlinks. |
| [L197](../src/april_repro/route_adjudication_audit.py#L197) | function/method | <code>_bundle_report(root: Path, paths: Sequence[str]) -&gt; dict[str, Any]</code> |  |
| [L228](../src/april_repro/route_adjudication_audit.py#L228) | function/method | <code>_bundle(root: Path, paths: Sequence[str]) -&gt; str</code> |  |
| [L232](../src/april_repro/route_adjudication_audit.py#L232) | function/method | <code>_strict_utc_iso(value: Any) -&gt; bool</code> |  |
| [L242](../src/april_repro/route_adjudication_audit.py#L242) | function/method | <code>_artifacts_are_git_ignored(root: Path) -&gt; bool</code> |  |
| [L257](../src/april_repro/route_adjudication_audit.py#L257) | function/method | <code>_typed_hash(field: str, records: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L297](../src/april_repro/route_adjudication_audit.py#L297) | function/method | <code>_canonical_hash(values: Sequence[str]) -&gt; str</code> |  |
| [L309](../src/april_repro/route_adjudication_audit.py#L309) | function/method | <code>_mapping_hash(input_sha: str, entries: Sequence[Mapping[str, Any]]) -&gt; str</code> |  |
| [L313](../src/april_repro/route_adjudication_audit.py#L313) | function/method | <code>_mapping_hash.key(entry: Mapping[str, Any]) -&gt; tuple[bytes, int, bytes]</code> |  |
| [L350](../src/april_repro/route_adjudication_audit.py#L350) | function/method | <code>_safe_child(directory: Path, name: Any, label: str) -&gt; Path</code> |  |
| [L359](../src/april_repro/route_adjudication_audit.py#L359) | function/method | <code>_load_config(root: Path) -&gt; dict[str, Any]</code> |  |
| [L443](../src/april_repro/route_adjudication_audit.py#L443) | function/method | <code>_preflight(root: Path, config: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L524](../src/april_repro/route_adjudication_audit.py#L524) | function/method | <code>_expected_lineage(config: Mapping[str, Any], preflight: Mapping[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L542](../src/april_repro/route_adjudication_audit.py#L542) | function/method | <code>_rebuild_from_review(review: Mapping[str, Any], preflight: Mapping[str, Any]) -&gt; tuple[list[dict[str, Any]], dict[str, int], bool]</code> |  |
| [L653](../src/april_repro/route_adjudication_audit.py#L653) | function/method | <code>audit_mapping_artifact(directory: Path, root: Path) -&gt; tuple[dict[str, Any], Path]</code> |  |

<a id="module-a0ad20cd70f0"></a>

## src/april_repro/route_adjudication_preregistration.py

[Open source](../src/april_repro/route_adjudication_preregistration.py)

Source module docstring:

> Machine report for the proposed D005 exact route-adjudication workflow.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L23](../src/april_repro/route_adjudication_preregistration.py#L23) | function/method | <code>read_potassium_route_adjudication_preregistration(root: Path) -&gt; dict[str, Any]</code> |  |
| [L28](../src/april_repro/route_adjudication_preregistration.py#L28) | function/method | <code>validate_potassium_route_adjudication_preregistration(config: Mapping[str, Any]) -&gt; list[str]</code> |  |
| [L33](../src/april_repro/route_adjudication_preregistration.py#L33) | function/method | <code>validate_potassium_route_adjudication_preregistration.expect(table: Any, key: str, value: Any, section: str) -&gt; None</code> |  |
| [L122](../src/april_repro/route_adjudication_preregistration.py#L122) | function/method | <code>potassium_route_adjudication_preregistration_report(root: Path) -&gt; dict[str, Any]</code> |  |

<a id="module-22acc79fcaef"></a>

## src/april_repro/sharded_source_closure.py

[Open source](../src/april_repro/sharded_source_closure.py)

Source module docstring:

> Same-snapshot event runner for query-200 source closure. The runner keeps the two discovery SELECTs, three global aggregate SELECTs, and either one unbucketed event SELECT or every subject-hash event bucket in one persistent PostgreSQL session and one REPEATABLE READ READ ONLY transaction. Database-derived values remain in memory until the transaction has explicitly rolled back and psql has exited cleanly. Only then are the private discovery, executed SQL, and merged public CSV written to disk.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L242](../src/april_repro/sharded_source_closure.py#L242) | function/method | <code>_now() -&gt; str</code> |  |
| [L246](../src/april_repro/sharded_source_closure.py#L246) | function/method | <code>_validate_bucket_count(bucket_count: Any) -&gt; int</code> |  |
| [L259](../src/april_repro/sharded_source_closure.py#L259) | function/method | <code>_validate_execution_mode(execution_mode: Any) -&gt; str</code> |  |
| [L268](../src/april_repro/sharded_source_closure.py#L268) | function/method | <code>_validate_detail_code_name(value: Any) -&gt; str &#124; None</code> |  |
| [L288](../src/april_repro/sharded_source_closure.py#L288) | function/method | <code>_parse_json_object(raw: Any, label: str) -&gt; dict[str, Any]</code> |  |
| [L298](../src/april_repro/sharded_source_closure.py#L298) | function/method | <code>_expected_review_stratum(item: Mapping[str, Any]) -&gt; str</code> |  |
| [L310](../src/april_repro/sharded_source_closure.py#L310) | function/method | <code>_extract_detail_code_dictionary(rows: list[dict[str, str]]) -&gt; tuple[list[dict[str, str]], list[dict[str, Any]]]</code> | Validate and remove 200e's private code-description flag handoff. |
| [L434](../src/april_repro/sharded_source_closure.py#L434) | function/method | <code>_detail_code_flag_values(values: list[dict[str, Any]]) -&gt; str</code> |  |
| [L473](../src/april_repro/sharded_source_closure.py#L473) | function/method | <code>_validate_discovery_vocabulary_sets(fragments: Mapping[str, list[dict[str, str]]], discovery: Mapping[str, Any]) -&gt; None</code> | Require public lexical vocabulary to equal all four private dictionaries. |
| [L513](../src/april_repro/sharded_source_closure.py#L513) | function/method | <code>_validate_event_dictionary_guard(rows: list[dict[str, str]], dictionary_count: int) -&gt; dict[str, int]</code> |  |
| [L565](../src/april_repro/sharded_source_closure.py#L565) | function/method | <code>_validate_bucket_dictionary_guard(rows: list[dict[str, str]], dictionary_count: int, bucket_index: int, bucket_count: int) -&gt; dict[str, int]</code> |  |
| [L598](../src/april_repro/sharded_source_closure.py#L598) | function/method | <code>_discovery_replacements(discovery: Mapping[str, Any]) -&gt; dict[str, str]</code> |  |
| [L640](../src/april_repro/sharded_source_closure.py#L640) | function/method | <code>render_known_template(template: str, discovery: Mapping[str, Any], template_kind: str, *, bucket_index: int &#124; None=None, bucket_count: int &#124; None=None) -&gt; str</code> | Render one reviewed template with its exact, single-use marker set. |
| [L685](../src/april_repro/sharded_source_closure.py#L685) | function/method | <code>_session_preamble() -&gt; str</code> |  |
| [L702](../src/april_repro/sharded_source_closure.py#L702) | function/method | <code>_aggregate_control(rendered: str, marker: str) -&gt; str</code> |  |
| [L717](../src/april_repro/sharded_source_closure.py#L717) | function/method | <code>_mode(path: Path) -&gt; str</code> |  |
| [L721](../src/april_repro/sharded_source_closure.py#L721) | function/method | <code>_remove_private_values(paths: list[Path]) -&gt; bool</code> |  |
| [L730](../src/april_repro/sharded_source_closure.py#L730) | function/method | <code>_bounded_add(current: int, addition: int, limit: int, label: str) -&gt; int</code> |  |
| [L744](../src/april_repro/sharded_source_closure.py#L744) | function/method | <code>_initial_stage(file: str) -&gt; dict[str, Any]</code> |  |
| [L754](../src/april_repro/sharded_source_closure.py#L754) | function/method | <code>_record_template(stage: dict[str, Any], raw: bytes) -&gt; str</code> |  |
| [L763](../src/april_repro/sharded_source_closure.py#L763) | function/method | <code>_record_render(stage: dict[str, Any], rendered: str) -&gt; None</code> |  |
| [L769](../src/april_repro/sharded_source_closure.py#L769) | function/method | <code>_record_control(stage: dict[str, Any], control: str) -&gt; None</code> |  |
| [L775](../src/april_repro/sharded_source_closure.py#L775) | function/method | <code>_run_frame(session: _PersistentPsql, stage: dict[str, Any], control: str, marker: str, byte_limit: int) -&gt; bytes</code> |  |
| [L797](../src/april_repro/sharded_source_closure.py#L797) | function/method | <code>_validate_merge_result(result: MergeResult, execution_mode: str, bucket_count: int &#124; None) -&gt; tuple[bytes, dict[str, Any]]</code> |  |
| [L870](../src/april_repro/sharded_source_closure.py#L870) | function/method | <code>_safe_scan_counts(execution_mode: str, bucket_count: int &#124; None) -&gt; dict[str, int]</code> |  |
| [L885](../src/april_repro/sharded_source_closure.py#L885) | function/method | <code>_record_merge_validation_failure(entry: dict[str, Any], stages: Mapping[str, Any], origin: str, code: MergeValidationErrorCode) -&gt; None</code> | Record only a closed error token and a runner-controlled origin. |
| [L909](../src/april_repro/sharded_source_closure.py#L909) | function/method | <code>run_source_closure(root: Path, *, execution_mode: str=DEFAULT_EXECUTION_MODE, bucket_count: int &#124; None=None) -&gt; dict[str, Any]</code> | Run exact query 200 and return terminal-safe metadata only. |
| [L1548](../src/april_repro/sharded_source_closure.py#L1548) | function/method | <code>run_sharded_source_closure(root: Path, bucket_count: int=DEFAULT_BUCKET_COUNT) -&gt; dict[str, Any]</code> | Compatibility entry point for the subject-bucket production mode. |

<a id="module-0ab5ba222660"></a>

## src/april_repro/sodium_episodes.py

[Open source](../src/april_repro/sodium_episodes.py)

Source module docstring:

> Independent sodium treatment-dose candidates, without a cohort or zero action. APRIL section 3.1 describes the four hours BEFORE treatment as context. This candidate branch integrates a fully observed start/confirmation/stop sequence; it does not truncate dose to a four-hour action window. A complete episode is a project interpretation, not an assertion that the authors used this algorithm. Input is the existing normalized Event interface. Identity, route, product and unit decisions remain upstream. A known single Administered quantity is kept separate: its charttime is not an observed infusion start or end.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L27](../src/april_repro/sodium_episodes.py#L27) | function/method | <code>_time(value)</code> |  |
| [L31](../src/april_repro/sodium_episodes.py#L31) | function/method | <code>_finite(value)</code> |  |
| [L35](../src/april_repro/sodium_episodes.py#L35) | function/method | <code>_decimal(value)</code> |  |
| [L39](../src/april_repro/sodium_episodes.py#L39) | function/method | <code>build_sodium_episodes(events)</code> | Return private candidate rows and an aggregate summary. |
| [L59](../src/april_repro/sodium_episodes.py#L59) | function/method | <code>build_sodium_episodes.emit(block, kind, reason, *, closed=False, dose=None, segments=None)</code> |  |
| [L91](../src/april_repro/sodium_episodes.py#L91) | function/method | <code>build_sodium_episodes.trusted_stop(event)</code> |  |
| [L95](../src/april_repro/sodium_episodes.py#L95) | function/method | <code>build_sodium_episodes.base_reason(block)</code> |  |

<a id="module-3367d4dcac3a"></a>

## src/april_repro/source_closure_merge.py

[Open source](../src/april_repro/source_closure_merge.py)

Source module docstring:

> Strict, deterministic merge for partitioned query-200 aggregate output. The database runner executes four kinds of SELECTs in one read-only snapshot: &#96;&#96;global_head&#96;&#96; &#96;&#96;closure_global_head_metadata&#96;&#96; plus head &#96;&#96;source_vocabulary&#96;&#96; rows. &#96;&#96;global_detail&#96;&#96; &#96;&#96;closure_global_detail_metadata&#96;&#96;, detail &#96;&#96;source_vocabulary&#96;&#96; rows, and &#96;&#96;local_product_code_shape&#96;&#96; rows. &#96;&#96;global_order&#96;&#96; &#96;&#96;closure_global_order_metadata&#96;&#96; plus pharmacy/prescription vocabulary. &#96;&#96;unbucketed_event&#96;&#96; (preferred) One &#96;&#96;closure_event_metadata&#96;&#96; control row, two safe admission diagnostic sections, and the four public event sections from the unbucketed event-only query. &#96;&#96;event_bucket_N&#96;&#96; (fallback) One &#96;&#96;closure_bucket_metadata&#96;&#96; control row, two safe admission diagnostic sections, and the four additive event sections for subject-hash bucket &#96;&#96;N&#96;&#96;. This module accepts only the four CSV columns produced by those SELECTs. It parses JSON with duplicate-key rejection, validates every internal schema, and then constructs the public closure rows. It deliberately knows the internal metadata counter names: changing a SQL output is therefore a contract change, not a silently accepted extra field. Bucket event rows are additive by exact dimensions. Integer counters are summed, except the fixed query-199 reference; boolean and string counters must match exactly. Global dictionary/code-shape rows are a disjoint union. The returned CSV has a stable section/records-descending/canonical-dimensions order.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L424](../src/april_repro/source_closure_merge.py#L424) | class | <code>MergeValidationErrorCode(StrEnum)</code> | Terminal-safe location of a query-200 merge-contract rejection. |
| [L447](../src/april_repro/source_closure_merge.py#L447) | class | <code>SourceClosureMergeError(ValueError)</code> | A fragment violates the strict query-200 merge contract. |
| [L450](../src/april_repro/source_closure_merge.py#L450) | function/method | <code>SourceClosureMergeError.__init__(self, message: str, *, code: MergeValidationErrorCode=MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED) -&gt; None</code> |  |
| [L464](../src/april_repro/source_closure_merge.py#L464) | function/method | <code>SourceClosureMergeError.code(self) -&gt; MergeValidationErrorCode</code> |  |
| [L467](../src/april_repro/source_closure_merge.py#L467) | function/method | <code>SourceClosureMergeError._assign_phase_code(self, code: MergeValidationErrorCode) -&gt; None</code> |  |
| [L473](../src/april_repro/source_closure_merge.py#L473) | class | <code>MergeResult()</code> | Validated public rows, deterministic CSV, and merge-control evidence. |
| [L481](../src/april_repro/source_closure_merge.py#L481) | function/method | <code>_canonical(value: Mapping[str, Any]) -&gt; str</code> |  |
| [L485](../src/april_repro/source_closure_merge.py#L485) | function/method | <code>_fail(message: str, *, code: MergeValidationErrorCode=MergeValidationErrorCode.UNCLASSIFIED_CONTRACT_REJECTED) -&gt; None</code> |  |
| [L496](../src/april_repro/source_closure_merge.py#L496) | function/method | <code>_validation_phase(code: MergeValidationErrorCode) -&gt; Iterator[None]</code> | Attach a safe phase code while preserving the detailed local error. |
| [L505](../src/april_repro/source_closure_merge.py#L505) | function/method | <code>_unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L517](../src/april_repro/source_closure_merge.py#L517) | function/method | <code>_reject_json_constant(value: str) -&gt; None</code> |  |
| [L524](../src/april_repro/source_closure_merge.py#L524) | function/method | <code>_parse_object(raw: Any, label: str) -&gt; dict[str, Any]</code> |  |
| [L547](../src/april_repro/source_closure_merge.py#L547) | function/method | <code>_reject_raw_keys(value: Any, label: str) -&gt; None</code> |  |
| [L566](../src/april_repro/source_closure_merge.py#L566) | function/method | <code>_parse_row(raw: Mapping[str, Any], origin: str, number: int) -&gt; dict[str, Any]</code> |  |
| [L585](../src/april_repro/source_closure_merge.py#L585) | function/method | <code>_normalise_one_fragment(origin: Any, raw_rows: Sequence[Mapping[str, Any]]) -&gt; tuple[str, list[dict[str, Any]]]</code> |  |
| [L610](../src/april_repro/source_closure_merge.py#L610) | function/method | <code>_normalise_fragments(fragments: Mapping[str, Sequence[Mapping[str, Any]]] &#124; Iterable[tuple[str, Sequence[Mapping[str, Any]]]], *, execution_mode: str, bucket_count: int &#124; None) -&gt; dict[str, list[dict[str, Any]]]</code> |  |
| [L642](../src/april_repro/source_closure_merge.py#L642) | function/method | <code>_resolve_execution_mode(execution_mode: str &#124; None, bucket_count: int &#124; None) -&gt; tuple[str, int &#124; None]</code> |  |
| [L659](../src/april_repro/source_closure_merge.py#L659) | function/method | <code>_check_schema(value: dict[str, Any], *, ints: set[str]=frozenset(), bools: Mapping[str, bool]={}, strings: Mapping[str, str]={}, label: str) -&gt; None</code> |  |
| [L677](../src/april_repro/source_closure_merge.py#L677) | function/method | <code>_single(rows: list[dict[str, Any]], section: str, origin: str) -&gt; dict[str, Any]</code> |  |
| [L684](../src/april_repro/source_closure_merge.py#L684) | function/method | <code>_empty_dimensions(row: dict[str, Any]) -&gt; None</code> |  |
| [L689](../src/april_repro/source_closure_merge.py#L689) | function/method | <code>_validate_metadata_row(row: dict[str, Any], ints: set[str], bools: Mapping[str, bool], strings: Mapping[str, str]={}) -&gt; None</code> |  |
| [L698](../src/april_repro/source_closure_merge.py#L698) | function/method | <code>_validate_controlled_name(value: Any, label: str, *, nullable: bool=True) -&gt; None</code> |  |
| [L712](../src/april_repro/source_closure_merge.py#L712) | function/method | <code>_validate_vocabulary(row: dict[str, Any], origin: str) -&gt; None</code> |  |
| [L762](../src/april_repro/source_closure_merge.py#L762) | function/method | <code>_validate_code_shape(row: dict[str, Any]) -&gt; None</code> |  |
| [L793](../src/april_repro/source_closure_merge.py#L793) | function/method | <code>_coarse(mask: int) -&gt; int</code> |  |
| [L797](../src/april_repro/source_closure_merge.py#L797) | function/method | <code>_expected_review(mask: int, valid_mask: int) -&gt; str</code> |  |
| [L818](../src/april_repro/source_closure_merge.py#L818) | function/method | <code>_validate_event_row(row: dict[str, Any]) -&gt; None</code> |  |
| [L896](../src/april_repro/source_closure_merge.py#L896) | function/method | <code>_validate_recovered_row(row: dict[str, Any]) -&gt; None</code> |  |
| [L937](../src/april_repro/source_closure_merge.py#L937) | function/method | <code>_validate_conservation_row(row: dict[str, Any]) -&gt; None</code> |  |
| [L957](../src/april_repro/source_closure_merge.py#L957) | function/method | <code>_validate_guard_row(row: dict[str, Any], expected: Mapping[str, bool &#124; str]=BUCKET_GUARD_VALUES) -&gt; None</code> |  |
| [L966](../src/april_repro/source_closure_merge.py#L966) | function/method | <code>_validate_admission_diagnostics(rows: list[dict[str, Any]], metadata: dict[str, Any], *, bucket_index: int &#124; None=None, bucket_count: int &#124; None=None) -&gt; None</code> | Validate the aggregate admission-link partition without exposing IDs. |
| [L1061](../src/april_repro/source_closure_merge.py#L1061) | function/method | <code>_validate_exact_values(actual: Mapping[str, Any], expected: Mapping[str, Any], label: str) -&gt; None</code> |  |
| [L1072](../src/april_repro/source_closure_merge.py#L1072) | function/method | <code>_validate_recovered_against_masks(recovered_rows: list[dict[str, Any]], mask_rows: list[dict[str, Any]], label: str) -&gt; None</code> |  |
| [L1110](../src/april_repro/source_closure_merge.py#L1110) | function/method | <code>_validate_one_bucket_conservation(rows: list[dict[str, Any]], metadata: dict[str, Any], conservation: dict[str, Any], guards: dict[str, Any]) -&gt; None</code> |  |
| [L1182](../src/april_repro/source_closure_merge.py#L1182) | function/method | <code>_merge_additive_rows(bucket_rows: list[list[dict[str, Any]]], section: str, int_keys: set[str], constant_int_keys: set[str]=frozenset()) -&gt; list[dict[str, Any]]</code> |  |
| [L1211](../src/april_repro/source_closure_merge.py#L1211) | function/method | <code>_validate_one_global_fragment(origin: str, rows: list[dict[str, Any]]) -&gt; tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L1238](../src/april_repro/source_closure_merge.py#L1238) | function/method | <code>_validate_global_fragments(fragments: dict[str, list[dict[str, Any]]]) -&gt; tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]</code> |  |
| [L1274](../src/april_repro/source_closure_merge.py#L1274) | function/method | <code>_validate_one_bucket_fragment(origin: str, rows: list[dict[str, Any]], index: int, bucket_count: int) -&gt; dict[str, Any]</code> |  |
| [L1341](../src/april_repro/source_closure_merge.py#L1341) | function/method | <code>_validate_bucket_fragments(fragments: dict[str, list[dict[str, Any]]], bucket_count: int) -&gt; tuple[list[list[dict[str, Any]]], dict[str, Any], dict[str, Any]]</code> |  |
| [L1447](../src/april_repro/source_closure_merge.py#L1447) | function/method | <code>_validate_unbucketed_fragment(fragments: dict[str, list[dict[str, Any]]]) -&gt; tuple[list[list[dict[str, Any]]], dict[str, Any], dict[str, Any]]</code> |  |
| [L1542](../src/april_repro/source_closure_merge.py#L1542) | function/method | <code>validate_source_closure_fragment(origin: str, rows: Sequence[Mapping[str, Any]], *, execution_mode: str, bucket_count: int &#124; None) -&gt; None</code> | Validate one query-200 fragment before the next SQL stage executes. |
| [L1592](../src/april_repro/source_closure_merge.py#L1592) | function/method | <code>_require_equal(values: Iterable[tuple[str, Any]], label: str) -&gt; Any</code> |  |
| [L1601](../src/april_repro/source_closure_merge.py#L1601) | function/method | <code>_assemble_metadata(metadata_rows: dict[str, dict[str, Any]], event_control: dict[str, Any], event_scan_count: int, metadata_constants: Mapping[str, Any] &#124; None) -&gt; dict[str, Any]</code> |  |
| [L1730](../src/april_repro/source_closure_merge.py#L1730) | function/method | <code>_postmerge_invariants(rows: list[dict[str, Any]], metadata_rows: dict[str, dict[str, Any]], bucket_totals: dict[str, Any]) -&gt; None</code> |  |
| [L1906](../src/april_repro/source_closure_merge.py#L1906) | function/method | <code>_public_row(row: dict[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L1913](../src/april_repro/source_closure_merge.py#L1913) | function/method | <code>_sort_rows(rows: list[dict[str, Any]]) -&gt; list[dict[str, Any]]</code> |  |
| [L1920](../src/april_repro/source_closure_merge.py#L1920) | function/method | <code>_to_csv(rows: list[dict[str, Any]]) -&gt; str</code> |  |
| [L1934](../src/april_repro/source_closure_merge.py#L1934) | function/method | <code>merge_source_closure_fragments(fragments: Mapping[str, Sequence[Mapping[str, Any]]] &#124; Iterable[tuple[str, Sequence[Mapping[str, Any]]]], *, bucket_count: int &#124; None=None, execution_mode: str &#124; None=None, metadata_constants: Mapping[str, Any] &#124; None=None) -&gt; MergeResult</code> | Validate and merge query-200 global and subject-bucket CSV rows. |

<a id="module-b4d49fe50ec6"></a>

## src/april_repro/staged_source_closure.py

[Open source](../src/april_repro/staged_source_closure.py)

Source module docstring:

> Three-stage, same-snapshot runner for potassium product source closure. The first SELECT discovers controlled source names. The second uses the exact detail-name set to derive identity-consistent local product-code seeds. The third computes aggregate closure evidence. All three SELECTs execute in one persistent psql session and one REPEATABLE READ READ ONLY transaction. Values discovered from MIMIC-IV are persisted only after an explicit rollback.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L47](../src/april_repro/staged_source_closure.py#L47) | function/method | <code>_now() -&gt; str</code> |  |
| [L51](../src/april_repro/staged_source_closure.py#L51) | function/method | <code>_write_private(path: Path, data: bytes) -&gt; None</code> |  |
| [L63](../src/april_repro/staged_source_closure.py#L63) | function/method | <code>_sha(data: bytes) -&gt; str</code> |  |
| [L67](../src/april_repro/staged_source_closure.py#L67) | function/method | <code>_hex_text(value: str) -&gt; str</code> | Produce a SQL expression without placing text inside a SQL literal. |
| [L80](../src/april_repro/staged_source_closure.py#L80) | function/method | <code>_unicode_literal(value: str, sql_type: str) -&gt; str</code> | Return a constant-foldable PostgreSQL literal with no raw source text. |
| [L94](../src/april_repro/staged_source_closure.py#L94) | function/method | <code>_constant_array(values: list[str], sql_type: str) -&gt; str</code> |  |
| [L103](../src/april_repro/staged_source_closure.py#L103) | function/method | <code>_values_one(values: list[str], column: str) -&gt; str</code> |  |
| [L111](../src/april_repro/staged_source_closure.py#L111) | function/method | <code>_native_values_one(values: list[str], column: str, sql_type: str) -&gt; str</code> | Render exact constant VALUES using the source column's native type. |
| [L120](../src/april_repro/staged_source_closure.py#L120) | function/method | <code>_values_seeds(values: list[dict[str, Any]]) -&gt; str</code> |  |
| [L135](../src/april_repro/staged_source_closure.py#L135) | function/method | <code>_values_indexed(discovery: dict[str, Any]) -&gt; str</code> |  |
| [L151](../src/april_repro/staged_source_closure.py#L151) | function/method | <code>_decode_unique_json(payload: bytes, stage_label: str) -&gt; dict[str, Any]</code> |  |
| [L155](../src/april_repro/staged_source_closure.py#L155) | function/method | <code>_decode_unique_json.unique_object(pairs: list[tuple[str, Any]]) -&gt; dict[str, Any]</code> |  |
| [L172](../src/april_repro/staged_source_closure.py#L172) | function/method | <code>_validate_snapshot_token(value: Any, stage_label: str) -&gt; str</code> |  |
| [L185](../src/april_repro/staged_source_closure.py#L185) | function/method | <code>_validate_common_controls(value: dict[str, Any], expected_stage: str, stage_label: str) -&gt; None</code> |  |
| [L202](../src/april_repro/staged_source_closure.py#L202) | function/method | <code>_validate_names_discovery(payload: bytes) -&gt; dict[str, Any]</code> |  |
| [L253](../src/april_repro/staged_source_closure.py#L253) | function/method | <code>_validate_detail_seed_discovery(payload: bytes, names: dict[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L320](../src/april_repro/staged_source_closure.py#L320) | function/method | <code>_assert_same_snapshot_controls(stages: dict[str, dict[str, Any]]) -&gt; str</code> |  |
| [L338](../src/april_repro/staged_source_closure.py#L338) | function/method | <code>_merge_discovery(names: dict[str, Any], seeds: dict[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L372](../src/april_repro/staged_source_closure.py#L372) | function/method | <code>render_detail_seed_discovery(template: str, names: dict[str, Any]) -&gt; str</code> |  |
| [L385](../src/april_repro/staged_source_closure.py#L385) | function/method | <code>render_stage_b(template: str, discovery: dict[str, Any]) -&gt; str</code> |  |
| [L417](../src/april_repro/staged_source_closure.py#L417) | class | <code>_PersistentPsql()</code> |  |
| [L418](../src/april_repro/staged_source_closure.py#L418) | function/method | <code>_PersistentPsql.__init__(self, client: PsqlClient, stderr_path: Path &#124; None)</code> |  |
| [L449](../src/april_repro/staged_source_closure.py#L449) | function/method | <code>_PersistentPsql.send(self, sql: str) -&gt; None</code> |  |
| [L455](../src/april_repro/staged_source_closure.py#L455) | function/method | <code>_PersistentPsql.frame(self, marker: str, timeout: float, byte_limit: int) -&gt; bytes</code> |  |
| [L504](../src/april_repro/staged_source_closure.py#L504) | function/method | <code>_PersistentPsql.confirm_rollback(self, marker: str, timeout: float=10) -&gt; None</code> |  |
| [L510](../src/april_repro/staged_source_closure.py#L510) | function/method | <code>_PersistentPsql.close(self) -&gt; int</code> |  |
| [L533](../src/april_repro/staged_source_closure.py#L533) | function/method | <code>_decode_payload_frame(frame: bytes, column: str, stage_label: str) -&gt; bytes</code> |  |
| [L554](../src/april_repro/staged_source_closure.py#L554) | function/method | <code>_parse_names_frame(frame: bytes) -&gt; dict[str, Any]</code> |  |
| [L560](../src/april_repro/staged_source_closure.py#L560) | function/method | <code>_parse_detail_seed_frame(frame: bytes, names: dict[str, Any]) -&gt; dict[str, Any]</code> |  |
| [L571](../src/april_repro/staged_source_closure.py#L571) | function/method | <code>_parse_result_frame(frame: bytes) -&gt; tuple[str, list[dict[str, str]], dict[str, str]]</code> |  |
| [L612](../src/april_repro/staged_source_closure.py#L612) | function/method | <code>run_staged_source_closure(root: Path) -&gt; dict[str, Any]</code> | Run query 200 and return terminal-safe execution metadata only. |

<a id="module-dbc3e895c1bc"></a>

## src/april_repro/treatment_decisions.py

[Open source](../src/april_repro/treatment_decisions.py)

Source module docstring:

> Treatment-anchored decisions plus independent four-hour zero selection cells. These are declared implementation choices for APRIL, not recovered author code. Four hours describes pretreatment context; it never truncates a positive dose. Missing pretreatment labs are retained. Clinical SQL selects the first post lab and makes its own eligibility decision, which this module cannot override.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L47](../src/april_repro/treatment_decisions.py#L47) | function/method | <code>_time(value)</code> |  |
| [L59](../src/april_repro/treatment_decisions.py#L59) | function/method | <code>_iso(value)</code> |  |
| [L63](../src/april_repro/treatment_decisions.py#L63) | function/method | <code>_true(value)</code> |  |
| [L67](../src/april_repro/treatment_decisions.py#L67) | function/method | <code>_dose(value)</code> |  |
| [L75](../src/april_repro/treatment_decisions.py#L75) | function/method | <code>_decimal(value)</code> |  |
| [L80](../src/april_repro/treatment_decisions.py#L80) | function/method | <code>_id(*parts)</code> |  |
| [L85](../src/april_repro/treatment_decisions.py#L85) | function/method | <code>_validate_events(events, task)</code> |  |
| [L99](../src/april_repro/treatment_decisions.py#L99) | function/method | <code>_candidate(task, kind, subject, admission, start, end, dose, sources, quantity_basis, timing_basis, observed=False, segments=None)</code> |  |
| [L115](../src/april_repro/treatment_decisions.py#L115) | function/method | <code>make_positive_candidates(events, task)</code> | Return usable positive source candidates; clinical eligibility is separate. |
| [L173](../src/april_repro/treatment_decisions.py#L173) | function/method | <code>_checked_candidate(candidate, source_index, task)</code> |  |
| [L200](../src/april_repro/treatment_decisions.py#L200) | function/method | <code>build_treatment_decisions(clinical_positive_rows, positive_candidates, zero_clinical_rows, events, task)</code> | Join complete clinical batches and apply source-aware co-treatment rules. |
| [L249](../src/april_repro/treatment_decisions.py#L249) | function/method | <code>build_treatment_decisions.emit(row, candidate=None)</code> |  |

<a id="module-8608c525021e"></a>

## src/april_repro/units.py

[Open source](../src/april_repro/units.py)

Source module docstring:

> Physical unit conversion; this module does not assign treatment actions. 3% Sodium Chloride Injection labels specify sodium 513 mEq/L (0.513 mEq/mL). Source: DailyMed setid f2475fa3-ab1d-4b81-8127-b58cd0790a54, DESCRIPTION, verified 2026-10-11. This rounded label concentration is the declared basis. Callers must independently establish solution identity and administered volume. An order quantity, bag capacity or diagnostic rate integral is not established actual volume merely because it can be passed to this arithmetic function.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L17](../src/april_repro/units.py#L17) | function/method | <code>sodium_meq_from_3pct_saline_ml(volume_ml: int &#124; float) -&gt; float</code> | Convert nonnegative mL of verified 3% NaCl to sodium mEq; no binning. |

<a id="module-001e61d97d9d"></a>

## tests/__init__.py

[Open source](../tests/__init__.py)

Source module docstring:

> Project-local test package for locked synthetic attestations.

No named function or class definitions in this file.

<a id="module-042e77e91561"></a>

## tests/test_clinical_baseline.py

[Open source](../tests/test_clinical_baseline.py)

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L16](../tests/test_clinical_baseline.py#L16) | class | <code>ClinicalBaselineTests(unittest.TestCase)</code> |  |
| [L17](../tests/test_clinical_baseline.py#L17) | function/method | <code>ClinicalBaselineTests.test_majority_accuracy_does_not_hide_positive_action_failure(self)</code> |  |
| [L28](../tests/test_clinical_baseline.py#L28) | function/method | <code>ClinicalBaselineTests.test_empty_validation_has_no_accuracy(self)</code> |  |
| [L34](../tests/test_clinical_baseline.py#L34) | function/method | <code>ClinicalBaselineTests.test_invalid_probability_and_unknown_action_rejected(self)</code> |  |
| [L40](../tests/test_clinical_baseline.py#L40) | function/method | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip(self)</code> |  |
| [L41](../tests/test_clinical_baseline.py#L41) | class | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Data()</code> |  |
| [L48](../tests/test_clinical_baseline.py#L48) | class | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Policy()</code> |  |
| [L50](../tests/test_clinical_baseline.py#L50) | function/method | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Policy.to_dict(self)</code> |  |
| [L51](../tests/test_clinical_baseline.py#L51) | function/method | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Policy.predict_proba(self, X)</code> |  |
| [L54](../tests/test_clinical_baseline.py#L54) | class | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Reward()</code> |  |
| [L56](../tests/test_clinical_baseline.py#L56) | function/method | <code>ClinicalBaselineTests.test_point_dm_uses_raw_context_separately_and_does_not_clip.Reward.predict_action_values(self, X)</code> |  |
| [L71](../tests/test_clinical_baseline.py#L71) | function/method | <code>ClinicalBaselineTests.test_empty_target_and_nonconverged_policy_are_not_estimable(self)</code> |  |
| [L72](../tests/test_clinical_baseline.py#L72) | class | <code>ClinicalBaselineTests.test_empty_target_and_nonconverged_policy_are_not_estimable.Data()</code> |  |
| [L75](../tests/test_clinical_baseline.py#L75) | class | <code>ClinicalBaselineTests.test_empty_target_and_nonconverged_policy_are_not_estimable.Policy()</code> |  |
| [L77](../tests/test_clinical_baseline.py#L77) | function/method | <code>ClinicalBaselineTests.test_empty_target_and_nonconverged_policy_are_not_estimable.Policy.to_dict(self)</code> |  |
| [L78](../tests/test_clinical_baseline.py#L78) | class | <code>ClinicalBaselineTests.test_empty_target_and_nonconverged_policy_are_not_estimable.Reward()</code> |  |
| [L85](../tests/test_clinical_baseline.py#L85) | function/method | <code>ClinicalBaselineTests.test_recorded_parameter_change_cannot_silently_run_different_model(self)</code> |  |
| [L92](../tests/test_clinical_baseline.py#L92) | function/method | <code>ClinicalBaselineTests.test_nested_nonconvergence_is_respected_and_constant_needs_no_solver(self)</code> |  |
| [L93](../tests/test_clinical_baseline.py#L93) | class | <code>ClinicalBaselineTests.test_nested_nonconvergence_is_respected_and_constant_needs_no_solver.Model()</code> |  |
| [L95](../tests/test_clinical_baseline.py#L95) | function/method | <code>ClinicalBaselineTests.test_nested_nonconvergence_is_respected_and_constant_needs_no_solver.Model.__init__(self, state)</code> |  |
| [L96](../tests/test_clinical_baseline.py#L96) | function/method | <code>ClinicalBaselineTests.test_nested_nonconvergence_is_respected_and_constant_needs_no_solver.Model.to_dict(self)</code> |  |

<a id="module-7eaa37e3d998"></a>

## tests/test_clinical_bootstrap.py

[Open source](../tests/test_clinical_bootstrap.py)

Source module docstring:

> Synthetic clinical draw tests with the actual declared fitting backend.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L24](../tests/test_clinical_bootstrap.py#L24) | class | <code>Dataset()</code> |  |
| [L25](../tests/test_clinical_bootstrap.py#L25) | function/method | <code>Dataset.__init__(self)</code> |  |
| [L46](../tests/test_clinical_bootstrap.py#L46) | function/method | <code>Dataset.mask(self, split, role, fold=None)</code> |  |
| [L51](../tests/test_clinical_bootstrap.py#L51) | class | <code>FixedPopulation()</code> | Only synthetic tests supply known cluster multiplicities. |
| [L53](../tests/test_clinical_bootstrap.py#L53) | function/method | <code>FixedPopulation.__init__(self, original, counts)</code> |  |
| [L57](../tests/test_clinical_bootstrap.py#L57) | function/method | <code>FixedPopulation.__getattr__(self, name)</code> |  |
| [L60](../tests/test_clinical_bootstrap.py#L60) | function/method | <code>FixedPopulation.draw(self, draw_id, *, seed)</code> |  |
| [L70](../tests/test_clinical_bootstrap.py#L70) | class | <code>ClinicalBootstrapTests(unittest.TestCase)</code> |  |
| [L71](../tests/test_clinical_bootstrap.py#L71) | function/method | <code>ClinicalBootstrapTests.setUp(self)</code> |  |
| [L74](../tests/test_clinical_bootstrap.py#L74) | function/method | <code>ClinicalBootstrapTests.populations(self, counts=None)</code> |  |
| [L80](../tests/test_clinical_bootstrap.py#L80) | function/method | <code>ClinicalBootstrapTests.test_success_reconstructs_dm_from_saved_models_and_same_evaluation(self)</code> |  |
| [L99](../tests/test_clinical_bootstrap.py#L99) | function/method | <code>ClinicalBootstrapTests.test_unequal_clusters_use_repeated_event_mean_not_patient_mean(self)</code> |  |
| [L106](../tests/test_clinical_bootstrap.py#L106) | function/method | <code>ClinicalBootstrapTests.test_sodium_uses_all_six_paper_action_columns_with_missing_actions(self)</code> |  |
| [L117](../tests/test_clinical_bootstrap.py#L117) | function/method | <code>ClinicalBootstrapTests.test_each_model_refits_preprocessing_on_its_resampled_train_only(self)</code> |  |
| [L132](../tests/test_clinical_bootstrap.py#L132) | function/method | <code>ClinicalBootstrapTests.test_no_behavior_clone_and_one_reward_fit(self)</code> |  |
| [L140](../tests/test_clinical_bootstrap.py#L140) | function/method | <code>ClinicalBootstrapTests.test_constant_policy_and_missing_actions_are_accepted_without_redraw(self)</code> |  |
| [L152](../tests/test_clinical_bootstrap.py#L152) | function/method | <code>ClinicalBootstrapTests.test_policy_nonconvergence_retains_model_and_omits_numeric_result(self)</code> |  |
| [L169](../tests/test_clinical_bootstrap.py#L169) | function/method | <code>ClinicalBootstrapTests.test_reward_unavailable_is_failed_with_both_fitted_states(self)</code> |  |
| [L179](../tests/test_clinical_bootstrap.py#L179) | function/method | <code>ClinicalBootstrapTests.test_empty_original_population_rejected_before_training(self)</code> |  |
| [L185](../tests/test_clinical_bootstrap.py#L185) | function/method | <code>ClinicalBootstrapTests.test_invalid_probability_does_not_return_partial_numeric_result(self)</code> |  |
| [L186](../tests/test_clinical_bootstrap.py#L186) | function/method | <code>ClinicalBootstrapTests.test_invalid_probability_does_not_return_partial_numeric_result.invalid(model, values)</code> |  |
| [L197](../tests/test_clinical_bootstrap.py#L197) | function/method | <code>ClinicalBootstrapTests.test_ols_predictions_are_counted_outside_range_and_never_clipped(self)</code> |  |
| [L206](../tests/test_clinical_bootstrap.py#L206) | function/method | <code>ClinicalBootstrapTests.test_prediction_batch_size_changes_neither_population_nor_estimator(self)</code> |  |
| [L216](../tests/test_clinical_bootstrap.py#L216) | function/method | <code>ClinicalBootstrapTests.test_mixed_input_populations_and_invalid_batches_rejected(self)</code> |  |
| [L229](../tests/test_clinical_bootstrap.py#L229) | function/method | <code>ClinicalBootstrapTests.test_unexpected_fit_exception_propagates_to_driver(self)</code> |  |

<a id="module-23967c776c01"></a>

## tests/test_clinical_bootstrap_runner.py

[Open source](../tests/test_clinical_bootstrap_runner.py)

Source module docstring:

> Tiny synthetic fit/commit/resume checks; no database or clinical files.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L33](../tests/test_clinical_bootstrap_runner.py#L33) | class | <code>ClinicalBootstrapRunnerTests(unittest.TestCase)</code> |  |
| [L34](../tests/test_clinical_bootstrap_runner.py#L34) | function/method | <code>ClinicalBootstrapRunnerTests.setUp(self)</code> |  |
| [L68](../tests/test_clinical_bootstrap_runner.py#L68) | function/method | <code>ClinicalBootstrapRunnerTests.synthetic_dataset(self)</code> |  |
| [L92](../tests/test_clinical_bootstrap_runner.py#L92) | function/method | <code>ClinicalBootstrapRunnerTests.invoke(self, *, resume=None, limit=1)</code> |  |
| [L99](../tests/test_clinical_bootstrap_runner.py#L99) | function/method | <code>ClinicalBootstrapRunnerTests.manifest(self, artifact)</code> |  |
| [L102](../tests/test_clinical_bootstrap_runner.py#L102) | function/method | <code>ClinicalBootstrapRunnerTests.engine(self, dataset, populations, draw_id, **kwargs)</code> |  |
| [L107](../tests/test_clinical_bootstrap_runner.py#L107) | function/method | <code>ClinicalBootstrapRunnerTests.test_pilot_resume_preserves_failed_draws_and_skips_empty_population(self)</code> |  |
| [L108](../tests/test_clinical_bootstrap_runner.py#L108) | function/method | <code>ClinicalBootstrapRunnerTests.test_pilot_resume_preserves_failed_draws_and_skips_empty_population.engine(dataset, populations, draw_id, **kwargs)</code> |  |
| [L148](../tests/test_clinical_bootstrap_runner.py#L148) | function/method | <code>ClinicalBootstrapRunnerTests.test_resume_rejects_changed_input_code_and_saved_code_before_new_fit(self)</code> |  |
| [L166](../tests/test_clinical_bootstrap_runner.py#L166) | function/method | <code>ClinicalBootstrapRunnerTests.test_resume_rejects_committed_payload_and_consistently_altered_result(self)</code> |  |
| [L188](../tests/test_clinical_bootstrap_runner.py#L188) | function/method | <code>ClinicalBootstrapRunnerTests.test_atomic_draw_committed_before_manifest_checkpoint_is_recovered_without_replacement(self)</code> |  |
| [L204](../tests/test_clinical_bootstrap_runner.py#L204) | function/method | <code>ClinicalBootstrapRunnerTests.test_unexpected_exception_retains_failed_id_and_resume_moves_forward(self)</code> |  |
| [L205](../tests/test_clinical_bootstrap_runner.py#L205) | function/method | <code>ClinicalBootstrapRunnerTests.test_unexpected_exception_retains_failed_id_and_resume_moves_forward.broken(dataset, populations, draw_id, **kwargs)</code> |  |

<a id="module-d35afe662435"></a>

## tests/test_clinical_bootstrap_statistics.py

[Open source](../tests/test_clinical_bootstrap_statistics.py)

Source module docstring:

> Synthetic arithmetic and draw-accounting checks; no clinical data access.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L18](../tests/test_clinical_bootstrap_statistics.py#L18) | function/method | <code>draw(draw_id, value, reference)</code> |  |
| [L28](../tests/test_clinical_bootstrap_statistics.py#L28) | class | <code>BootstrapStatisticsTests(unittest.TestCase)</code> |  |
| [L29](../tests/test_clinical_bootstrap_statistics.py#L29) | function/method | <code>BootstrapStatisticsTests.test_rmse_not_mae_and_sample_sd_not_mean_se(self)</code> |  |
| [L41](../tests/test_clinical_bootstrap_statistics.py#L41) | function/method | <code>BootstrapStatisticsTests.test_delta_mcse_formula_and_labeled_one_se_bounds(self)</code> |  |
| [L49](../tests/test_clinical_bootstrap_statistics.py#L49) | function/method | <code>BootstrapStatisticsTests.test_equal_squared_errors_have_zero_mcse_but_nonzero_error_sd(self)</code> |  |
| [L55](../tests/test_clinical_bootstrap_statistics.py#L55) | function/method | <code>BootstrapStatisticsTests.test_all_zero_errors_have_zero_mcse_even_with_varying_values(self)</code> |  |
| [L61](../tests/test_clinical_bootstrap_statistics.py#L61) | function/method | <code>BootstrapStatisticsTests.test_one_draw_has_rmse_but_no_sd_mcse_or_bounds_including_zero_error(self)</code> |  |
| [L69](../tests/test_clinical_bootstrap_statistics.py#L69) | function/method | <code>BootstrapStatisticsTests.test_partial_metrics_never_become_primary_and_missing_draws_are_pending(self)</code> |  |
| [L81](../tests/test_clinical_bootstrap_statistics.py#L81) | function/method | <code>BootstrapStatisticsTests.test_failed_and_pending_are_separate_and_null_results_allowed(self)</code> |  |
| [L95](../tests/test_clinical_bootstrap_statistics.py#L95) | function/method | <code>BootstrapStatisticsTests.test_all_terminal_with_failure_is_still_incomplete(self)</code> |  |
| [L101](../tests/test_clinical_bootstrap_statistics.py#L101) | function/method | <code>BootstrapStatisticsTests.test_empty_records_are_all_pending_not_a_population_diagnosis(self)</code> |  |
| [L111](../tests/test_clinical_bootstrap_statistics.py#L111) | function/method | <code>BootstrapStatisticsTests.test_no_completed_records_never_produce_diagnostic_metrics(self)</code> |  |
| [L116](../tests/test_clinical_bootstrap_statistics.py#L116) | function/method | <code>BootstrapStatisticsTests.test_duplicate_ids_rejected_across_statuses_instead_of_resume_overwrite(self)</code> |  |
| [L121](../tests/test_clinical_bootstrap_statistics.py#L121) | function/method | <code>BootstrapStatisticsTests.test_out_of_range_and_noninteger_draw_ids_rejected(self)</code> |  |
| [L126](../tests/test_clinical_bootstrap_statistics.py#L126) | function/method | <code>BootstrapStatisticsTests.test_planned_draw_count_must_be_positive_integer(self)</code> |  |
| [L131](../tests/test_clinical_bootstrap_statistics.py#L131) | function/method | <code>BootstrapStatisticsTests.test_unknown_status_and_nonmapping_records_rejected(self)</code> |  |
| [L136](../tests/test_clinical_bootstrap_statistics.py#L136) | function/method | <code>BootstrapStatisticsTests.test_all_three_complete_fields_must_be_finite_real_numbers(self)</code> |  |
| [L148](../tests/test_clinical_bootstrap_statistics.py#L148) | function/method | <code>BootstrapStatisticsTests.test_failed_or_pending_cannot_smuggle_numeric_results(self)</code> |  |
| [L154](../tests/test_clinical_bootstrap_statistics.py#L154) | function/method | <code>BootstrapStatisticsTests.test_signed_error_consistency_and_normal_float_roundoff(self)</code> |  |
| [L163](../tests/test_clinical_bootstrap_statistics.py#L163) | function/method | <code>BootstrapStatisticsTests.test_sorting_generator_json_serializability_and_no_input_mutation(self)</code> |  |
| [L171](../tests/test_clinical_bootstrap_statistics.py#L171) | function/method | <code>BootstrapStatisticsTests.test_large_and_small_finite_errors_do_not_square_overflow_or_underflow(self)</code> |  |
| [L180](../tests/test_clinical_bootstrap_statistics.py#L180) | function/method | <code>BootstrapStatisticsTests.test_mathematically_unrepresentable_difference_or_sd_is_rejected(self)</code> |  |

<a id="module-f0bcca423fb6"></a>

## tests/test_clinical_dataset.py

[Open source](../tests/test_clinical_dataset.py)

Source module docstring:

> Synthetic private-artifact loader tests; no database or patient data.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L23](../tests/test_clinical_dataset.py#L23) | class | <code>ClinicalDatasetTests(unittest.TestCase)</code> |  |
| [L24](../tests/test_clinical_dataset.py#L24) | function/method | <code>ClinicalDatasetTests.setUp(self)</code> |  |
| [L30](../tests/test_clinical_dataset.py#L30) | function/method | <code>ClinicalDatasetTests.write_csv(self, name, columns, rows)</code> |  |
| [L36](../tests/test_clinical_dataset.py#L36) | function/method | <code>ClinicalDatasetTests.make_fixture(self, task='potassium', *, excluded_gender=False)</code> |  |
| [L85](../tests/test_clinical_dataset.py#L85) | function/method | <code>ClinicalDatasetTests.refresh(self)</code> |  |
| [L92](../tests/test_clinical_dataset.py#L92) | function/method | <code>ClinicalDatasetTests.change_csv(self, name, function)</code> |  |
| [L100](../tests/test_clinical_dataset.py#L100) | function/method | <code>ClinicalDatasetTests.test_event_id_join_with_independently_reordered_outcomes_and_splits(self)</code> |  |
| [L109](../tests/test_clinical_dataset.py#L109) | function/method | <code>ClinicalDatasetTests.test_compact_types_feature_order_and_missing_preservation(self)</code> |  |
| [L123](../tests/test_clinical_dataset.py#L123) | function/method | <code>ClinicalDatasetTests.test_masks_select_declared_patient_role_and_fold(self)</code> |  |
| [L135](../tests/test_clinical_dataset.py#L135) | function/method | <code>ClinicalDatasetTests.test_sodium_actions_and_rewards(self)</code> |  |
| [L141](../tests/test_clinical_dataset.py#L141) | function/method | <code>ClinicalDatasetTests.test_valid_excluded_role_and_missing_gender_preserved(self)</code> |  |
| [L147](../tests/test_clinical_dataset.py#L147) | function/method | <code>ClinicalDatasetTests.test_incomplete_or_unsupported_artifact_rejected(self)</code> |  |
| [L157](../tests/test_clinical_dataset.py#L157) | function/method | <code>ClinicalDatasetTests.test_modified_csv_without_updated_hash_rejected(self)</code> |  |
| [L163](../tests/test_clinical_dataset.py#L163) | function/method | <code>ClinicalDatasetTests.test_groups_hash_checked_without_parsing_groups(self)</code> |  |
| [L168](../tests/test_clinical_dataset.py#L168) | function/method | <code>ClinicalDatasetTests.test_duplicate_feature_keys_rejected(self)</code> |  |
| [L173](../tests/test_clinical_dataset.py#L173) | function/method | <code>ClinicalDatasetTests.test_duplicate_outcome_keys_rejected(self)</code> |  |
| [L178](../tests/test_clinical_dataset.py#L178) | function/method | <code>ClinicalDatasetTests.test_outcome_identity_or_unknown_key_rejected(self)</code> |  |
| [L186](../tests/test_clinical_dataset.py#L186) | function/method | <code>ClinicalDatasetTests.test_outcome_missing_event_rejected(self)</code> |  |
| [L191](../tests/test_clinical_dataset.py#L191) | function/method | <code>ClinicalDatasetTests.test_outcome_anchor_must_match_feature_clock(self)</code> |  |
| [L196](../tests/test_clinical_dataset.py#L196) | function/method | <code>ClinicalDatasetTests.test_action_support_and_finite_post_lab_enforced(self)</code> |  |
| [L204](../tests/test_clinical_dataset.py#L204) | function/method | <code>ClinicalDatasetTests.test_feature_unknown_categories_and_explicit_nonfinite_rejected(self)</code> |  |
| [L212](../tests/test_clinical_dataset.py#L212) | function/method | <code>ClinicalDatasetTests.test_all_fifteen_feature_columns_required(self)</code> |  |
| [L219](../tests/test_clinical_dataset.py#L219) | function/method | <code>ClinicalDatasetTests.test_unknown_split_role_and_fold_labels_rejected(self)</code> |  |
| [L226](../tests/test_clinical_dataset.py#L226) | function/method | <code>ClinicalDatasetTests.test_split_identity_and_action_mismatch_rejected(self)</code> |  |
| [L233](../tests/test_clinical_dataset.py#L233) | function/method | <code>ClinicalDatasetTests.test_duplicate_event_split_pair_rejected(self)</code> |  |
| [L238](../tests/test_clinical_dataset.py#L238) | function/method | <code>ClinicalDatasetTests.test_missing_split_assignment_rejected(self)</code> |  |
| [L243](../tests/test_clinical_dataset.py#L243) | function/method | <code>ClinicalDatasetTests.test_patient_role_leakage_rejected(self)</code> |  |
| [L244](../tests/test_clinical_dataset.py#L244) | function/method | <code>ClinicalDatasetTests.test_patient_role_leakage_rejected.change(rows)</code> |  |
| [L251](../tests/test_clinical_dataset.py#L251) | function/method | <code>ClinicalDatasetTests.test_patient_fold_leakage_rejected(self)</code> |  |
| [L252](../tests/test_clinical_dataset.py#L252) | function/method | <code>ClinicalDatasetTests.test_patient_fold_leakage_rejected.change(rows)</code> |  |
| [L258](../tests/test_clinical_dataset.py#L258) | function/method | <code>ClinicalDatasetTests.test_manifest_population_and_split_counts_checked(self)</code> |  |

<a id="module-0e9d7257b534"></a>

## tests/test_clinical_dmplus.py

[Open source](../tests/test_clinical_dmplus.py)

Source module docstring:

> Synthetic clinical points and synthetic provider receipts only; no services.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L30](../tests/test_clinical_dmplus.py#L30) | function/method | <code>synthetic_dataset()</code> |  |
| [L44](../tests/test_clinical_dmplus.py#L44) | class | <code>ClinicalDMPlusTests(unittest.TestCase)</code> |  |
| [L45](../tests/test_clinical_dmplus.py#L45) | function/method | <code>ClinicalDMPlusTests.setUp(self)</code> |  |
| [L53](../tests/test_clinical_dmplus.py#L53) | function/method | <code>ClinicalDMPlusTests.test_zero_budget_is_exact_saved_model_identity(self)</code> |  |
| [L57](../tests/test_clinical_dmplus.py#L57) | function/method | <code>ClinicalDMPlusTests.test_equal_weight_ols_matches_oracle_with_fixed_factual_transform(self)</code> |  |
| [L77](../tests/test_clinical_dmplus.py#L77) | function/method | <code>ClinicalDMPlusTests.test_point_pair_uses_same_policy_and_same_target_events(self)</code> |  |
| [L92](../tests/test_clinical_dmplus.py#L92) | function/method | <code>ClinicalDMPlusTests.test_saved_dm_replay_rejects_changed_point_and_population(self)</code> |  |
| [L102](../tests/test_clinical_dmplus.py#L102) | function/method | <code>ClinicalDMPlusTests.test_empty_validation_stays_not_estimable(self)</code> |  |
| [L112](../tests/test_clinical_dmplus.py#L112) | function/method | <code>ClinicalDMPlusTests.test_augmentation_rejects_duplicate_source_leakage_and_observed_action(self)</code> |  |
| [L121](../tests/test_clinical_dmplus.py#L121) | function/method | <code>ClinicalDMPlusTests.fixture_evidence(self, *, malformed=False)</code> |  |
| [L130](../tests/test_clinical_dmplus.py#L130) | function/method | <code>ClinicalDMPlusTests.test_verified_receipts_join_only_cf_training_consumer_and_recompute_reward(self)</code> |  |
| [L143](../tests/test_clinical_dmplus.py#L143) | function/method | <code>ClinicalDMPlusTests.test_invalid_predictions_preserve_annotation_denominator(self)</code> |  |
| [L150](../tests/test_clinical_dmplus.py#L150) | function/method | <code>ClinicalDMPlusTests.test_forged_parsed_jsonl_even_with_rehashed_manifest_is_rejected(self)</code> |  |
| [L163](../tests/test_clinical_dmplus.py#L163) | function/method | <code>ClinicalDMPlusTests.test_modified_raw_reply_is_rejected_before_training(self)</code> |  |
| [L170](../tests/test_clinical_dmplus.py#L170) | function/method | <code>ClinicalDMPlusTests.test_join_rejects_other_dataset_observed_action_and_validation_membership(self)</code> |  |
| [L181](../tests/test_clinical_dmplus.py#L181) | function/method | <code>ClinicalDMPlusTests.test_cli_writes_private_local_artifacts_and_explicit_pilot_scope(self)</code> |  |
| [L207](../tests/test_clinical_dmplus.py#L207) | function/method | <code>ClinicalDMPlusTests.test_cli_writes_private_local_artifacts_and_explicit_pilot_scope.selected(dataset, evidence, split, model, index)</code> |  |

<a id="module-cd21bc5f39d5"></a>

## tests/test_clinical_dmplus_bootstrap.py

[Open source](../tests/test_clinical_dmplus_bootstrap.py)

Source module docstring:

> Synthetic same-patient CF bootstrap and saved-DM replay checks.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L28](../tests/test_clinical_dmplus_bootstrap.py#L28) | class | <code>ClinicalDMPlusBootstrapTests(unittest.TestCase)</code> |  |
| [L29](../tests/test_clinical_dmplus_bootstrap.py#L29) | function/method | <code>ClinicalDMPlusBootstrapTests.setUp(self)</code> |  |
| [L44](../tests/test_clinical_dmplus_bootstrap.py#L44) | function/method | <code>ClinicalDMPlusBootstrapTests.execute(self, annotations=None, **kwargs)</code> |  |
| [L48](../tests/test_clinical_dmplus_bootstrap.py#L48) | function/method | <code>ClinicalDMPlusBootstrapTests.test_cf_follows_patient_multiplicity_and_no_redraw_or_policy_fit(self)</code> |  |
| [L61](../tests/test_clinical_dmplus_bootstrap.py#L61) | function/method | <code>ClinicalDMPlusBootstrapTests.test_expanded_equal_weight_ols_matches_independent_row_oracle(self)</code> |  |
| [L86](../tests/test_clinical_dmplus_bootstrap.py#L86) | function/method | <code>ClinicalDMPlusBootstrapTests.test_empty_cache_budget_zero_preserves_exact_original_dm_and_model(self)</code> |  |
| [L94](../tests/test_clinical_dmplus_bootstrap.py#L94) | function/method | <code>ClinicalDMPlusBootstrapTests.test_unselected_source_patient_adds_no_annotation_and_no_refit(self)</code> |  |
| [L101](../tests/test_clinical_dmplus_bootstrap.py#L101) | function/method | <code>ClinicalDMPlusBootstrapTests.test_original_counts_order_or_metadata_change_rejected(self)</code> |  |
| [L123](../tests/test_clinical_dmplus_bootstrap.py#L123) | function/method | <code>ClinicalDMPlusBootstrapTests.test_wrong_saved_policy_baseline_or_draw_source_rejected(self)</code> |  |
| [L137](../tests/test_clinical_dmplus_bootstrap.py#L137) | function/method | <code>ClinicalDMPlusBootstrapTests.test_cache_validation_checks_even_patient_not_sampled(self)</code> |  |
| [L149](../tests/test_clinical_dmplus_bootstrap.py#L149) | function/method | <code>ClinicalDMPlusBootstrapTests.test_canonical_shared_reference_and_finite_json(self)</code> |  |
| [L157](../tests/test_clinical_dmplus_bootstrap.py#L157) | function/method | <code>ClinicalDMPlusBootstrapTests.test_invalid_budget_batch_and_original_failed_draw_rejected(self)</code> |  |
| [L168](../tests/test_clinical_dmplus_bootstrap.py#L168) | function/method | <code>ClinicalDMPlusBootstrapTests.test_changed_original_result_rejected_including_matching_fake_error(self)</code> |  |
| [L178](../tests/test_clinical_dmplus_bootstrap.py#L178) | function/method | <code>ClinicalDMPlusBootstrapTests.test_real_keyed_draw_sodium_action_scale_and_six_action_evaluation(self)</code> |  |
| [L206](../tests/test_clinical_dmplus_bootstrap.py#L206) | function/method | <code>ClinicalDMPlusBootstrapTests.test_batching_changes_neither_paired_membership_nor_value(self)</code> |  |

<a id="module-fee26819572e"></a>

## tests/test_clinical_dmplus_bootstrap_budgets_runner.py

[Open source](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py)

Source module docstring:

> Explicit model, source binding and resume checks; synthetic data, no API/DB.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L40](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L40) | class | <code>ModelBootstrapRunnerTests(unittest.TestCase)</code> |  |
| [L41](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L41) | function/method | <code>ModelBootstrapRunnerTests.setUp(self)</code> |  |
| [L102](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L102) | function/method | <code>ModelBootstrapRunnerTests.make_dataset(self)</code> |  |
| [L119](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L119) | function/method | <code>ModelBootstrapRunnerTests.invoke(self, *, resume=False, limit=1)</code> |  |
| [L124](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L124) | function/method | <code>ModelBootstrapRunnerTests.track(self, dataset, populations, original, *args, **kwargs)</code> |  |
| [L128](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L128) | function/method | <code>ModelBootstrapRunnerTests.manifest(self)</code> |  |
| [L131](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L131) | function/method | <code>ModelBootstrapRunnerTests.test_partial_resume_preserves_commits_and_skips_empty_split(self)</code> |  |
| [L148](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L148) | function/method | <code>ModelBootstrapRunnerTests.test_resume_rejects_source_manifests_and_bound_code_drift_before_fit(self)</code> |  |
| [L165](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L165) | function/method | <code>ModelBootstrapRunnerTests.test_existing_output_and_committed_model_cannot_be_replaced(self)</code> |  |
| [L181](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L181) | function/method | <code>ModelBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit(self)</code> |  |
| [L182](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L182) | function/method | <code>ModelBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit.broken(dataset, populations, original, *args, **kwargs)</code> |  |
| [L197](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L197) | function/method | <code>ModelBootstrapRunnerTests.test_atomic_commit_before_checkpoint_is_recovered_without_refit(self)</code> |  |
| [L207](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L207) | function/method | <code>ModelBootstrapRunnerTests.test_changed_fixed_annotation_cache_is_rejected_before_fit(self)</code> |  |
| [L215](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L215) | function/method | <code>ModelBootstrapRunnerTests.test_selected_model_flows_to_evidence_prefix_manifest_and_draws(self)</code> |  |
| [L225](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L225) | function/method | <code>ModelBootstrapRunnerTests.test_new_run_requires_supported_explicit_model_before_creating_output(self)</code> |  |
| [L232](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L232) | function/method | <code>ModelBootstrapRunnerTests.test_resume_rejects_explicit_model_override(self)</code> |  |
| [L238](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L238) | function/method | <code>ModelBootstrapRunnerTests.test_wrong_cached_source_model_rejected_before_fitting(self)</code> |  |
| [L247](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L247) | function/method | <code>ModelBootstrapRunnerTests.test_committed_draw_from_another_model_rejected_even_with_rebound_hash(self)</code> |  |
| [L259](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L259) | function/method | <code>ModelBootstrapRunnerTests.test_budget_reaches_core_and_new_output_namespace(self)</code> |  |
| [L270](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L270) | function/method | <code>ModelBootstrapRunnerTests.test_each_fixed_budget_uses_its_own_point_cache_and_record_binding(self)</code> |  |
| [L288](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L288) | function/method | <code>ModelBootstrapRunnerTests.test_new_budget_must_be_explicit_supported_integer(self)</code> |  |
| [L295](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L295) | function/method | <code>ModelBootstrapRunnerTests.test_resume_cannot_change_requested_budget(self)</code> |  |
| [L300](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L300) | function/method | <code>ModelBootstrapRunnerTests.test_committed_budget_mix_is_rejected_even_if_hash_is_rebound(self)</code> |  |
| [L310](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L310) | function/method | <code>ModelBootstrapRunnerTests.test_wrong_budget_cache_is_rejected_before_fit(self)</code> |  |
| [L318](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L318) | function/method | <code>ModelBootstrapRunnerTests.test_zero_budget_exactly_reuses_original_dm_and_payload(self)</code> |  |
| [L328](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L328) | function/method | <code>ModelBootstrapRunnerTests.test_suffix_must_match_budget_and_existing_namespace_is_rejected(self)</code> |  |
| [L335](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L335) | function/method | <code>ModelBootstrapRunnerTests.test_verification_output_requires_finite_draw_limit(self)</code> |  |
| [L343](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L343) | class | <code>ModelPointSourceTests(unittest.TestCase)</code> |  |
| [L344](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L344) | function/method | <code>ModelPointSourceTests.test_completed_point_requires_matching_declared_and_evidence_models(self)</code> |  |
| [L362](../tests/test_clinical_dmplus_bootstrap_budgets_runner.py#L362) | function/method | <code>ModelPointSourceTests.test_protocol_keeps_math_settings_and_exposes_only_fixed_prefix_budgets(self)</code> |  |

<a id="module-f0caf5012282"></a>

## tests/test_clinical_dmplus_bootstrap_models_runner.py

[Open source](../tests/test_clinical_dmplus_bootstrap_models_runner.py)

Source module docstring:

> Explicit model, source binding and resume checks; synthetic data, no API/DB.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L38](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L38) | class | <code>ModelBootstrapRunnerTests(unittest.TestCase)</code> |  |
| [L39](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L39) | function/method | <code>ModelBootstrapRunnerTests.setUp(self)</code> |  |
| [L102](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L102) | function/method | <code>ModelBootstrapRunnerTests.make_dataset(self)</code> |  |
| [L119](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L119) | function/method | <code>ModelBootstrapRunnerTests.invoke(self, *, resume=False, limit=1)</code> |  |
| [L124](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L124) | function/method | <code>ModelBootstrapRunnerTests.track(self, dataset, populations, original, *args, **kwargs)</code> |  |
| [L128](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L128) | function/method | <code>ModelBootstrapRunnerTests.manifest(self)</code> |  |
| [L131](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L131) | function/method | <code>ModelBootstrapRunnerTests.test_partial_resume_preserves_commits_and_skips_empty_split(self)</code> |  |
| [L148](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L148) | function/method | <code>ModelBootstrapRunnerTests.test_resume_rejects_source_manifests_and_bound_code_drift_before_fit(self)</code> |  |
| [L165](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L165) | function/method | <code>ModelBootstrapRunnerTests.test_existing_output_and_committed_model_cannot_be_replaced(self)</code> |  |
| [L181](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L181) | function/method | <code>ModelBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit(self)</code> |  |
| [L182](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L182) | function/method | <code>ModelBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit.broken(dataset, populations, original, *args, **kwargs)</code> |  |
| [L197](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L197) | function/method | <code>ModelBootstrapRunnerTests.test_atomic_commit_before_checkpoint_is_recovered_without_refit(self)</code> |  |
| [L207](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L207) | function/method | <code>ModelBootstrapRunnerTests.test_changed_fixed_annotation_cache_is_rejected_before_fit(self)</code> |  |
| [L215](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L215) | function/method | <code>ModelBootstrapRunnerTests.test_selected_model_flows_to_evidence_prefix_manifest_and_draws(self)</code> |  |
| [L225](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L225) | function/method | <code>ModelBootstrapRunnerTests.test_new_run_requires_supported_explicit_model_before_creating_output(self)</code> |  |
| [L232](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L232) | function/method | <code>ModelBootstrapRunnerTests.test_resume_rejects_explicit_model_override(self)</code> |  |
| [L238](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L238) | function/method | <code>ModelBootstrapRunnerTests.test_wrong_cached_source_model_rejected_before_fitting(self)</code> |  |
| [L247](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L247) | function/method | <code>ModelBootstrapRunnerTests.test_committed_draw_from_another_model_rejected_even_with_rebound_hash(self)</code> |  |
| [L261](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L261) | class | <code>ModelPointSourceTests(unittest.TestCase)</code> |  |
| [L262](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L262) | function/method | <code>ModelPointSourceTests.test_completed_point_requires_matching_declared_and_evidence_models(self)</code> |  |
| [L280](../tests/test_clinical_dmplus_bootstrap_models_runner.py#L280) | function/method | <code>ModelPointSourceTests.test_protocol_changes_only_model_dispatch_and_version_metadata(self)</code> |  |

<a id="module-bc6ceaaef39c"></a>

## tests/test_clinical_dmplus_bootstrap_runner.py

[Open source](../tests/test_clinical_dmplus_bootstrap_runner.py)

Source module docstring:

> Small local paired-runner resume checks, with synthetic data and no API/DB.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L38](../tests/test_clinical_dmplus_bootstrap_runner.py#L38) | class | <code>PairedBootstrapRunnerTests(unittest.TestCase)</code> |  |
| [L39](../tests/test_clinical_dmplus_bootstrap_runner.py#L39) | function/method | <code>PairedBootstrapRunnerTests.setUp(self)</code> |  |
| [L102](../tests/test_clinical_dmplus_bootstrap_runner.py#L102) | function/method | <code>PairedBootstrapRunnerTests.make_dataset(self)</code> |  |
| [L119](../tests/test_clinical_dmplus_bootstrap_runner.py#L119) | function/method | <code>PairedBootstrapRunnerTests.invoke(self, *, resume=False, limit=1)</code> |  |
| [L124](../tests/test_clinical_dmplus_bootstrap_runner.py#L124) | function/method | <code>PairedBootstrapRunnerTests.track(self, dataset, populations, original, *args, **kwargs)</code> |  |
| [L128](../tests/test_clinical_dmplus_bootstrap_runner.py#L128) | function/method | <code>PairedBootstrapRunnerTests.manifest(self)</code> |  |
| [L131](../tests/test_clinical_dmplus_bootstrap_runner.py#L131) | function/method | <code>PairedBootstrapRunnerTests.test_partial_resume_preserves_commits_and_skips_empty_split(self)</code> |  |
| [L148](../tests/test_clinical_dmplus_bootstrap_runner.py#L148) | function/method | <code>PairedBootstrapRunnerTests.test_resume_rejects_source_manifests_and_bound_code_drift_before_fit(self)</code> |  |
| [L165](../tests/test_clinical_dmplus_bootstrap_runner.py#L165) | function/method | <code>PairedBootstrapRunnerTests.test_existing_output_and_committed_model_cannot_be_replaced(self)</code> |  |
| [L181](../tests/test_clinical_dmplus_bootstrap_runner.py#L181) | function/method | <code>PairedBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit(self)</code> |  |
| [L182](../tests/test_clinical_dmplus_bootstrap_runner.py#L182) | function/method | <code>PairedBootstrapRunnerTests.test_failed_draw_identity_survives_resume_without_refit.broken(dataset, populations, original, *args, **kwargs)</code> |  |
| [L197](../tests/test_clinical_dmplus_bootstrap_runner.py#L197) | function/method | <code>PairedBootstrapRunnerTests.test_atomic_commit_before_checkpoint_is_recovered_without_refit(self)</code> |  |
| [L207](../tests/test_clinical_dmplus_bootstrap_runner.py#L207) | function/method | <code>PairedBootstrapRunnerTests.test_changed_fixed_annotation_cache_is_rejected_before_fit(self)</code> |  |

<a id="module-b7094df15a13"></a>

## tests/test_clinical_dmplus_bootstrap_statistics.py

[Open source](../tests/test_clinical_dmplus_bootstrap_statistics.py)

Source module docstring:

> Synthetic paired arithmetic, denominator and identity regression tests.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L19](../tests/test_clinical_dmplus_bootstrap_statistics.py#L19) | function/method | <code>draw(draw_id, value, reference=0.0, **extra)</code> |  |
| [L25](../tests/test_clinical_dmplus_bootstrap_statistics.py#L25) | class | <code>PairedBootstrapStatisticsTests(unittest.TestCase)</code> |  |
| [L26](../tests/test_clinical_dmplus_bootstrap_statistics.py#L26) | function/method | <code>PairedBootstrapStatisticsTests.summary(self, dm, plus, **kwargs)</code> |  |
| [L31](../tests/test_clinical_dmplus_bootstrap_statistics.py#L31) | function/method | <code>PairedBootstrapStatisticsTests.test_rmse_uses_all_squared_errors_and_existing_delta_mcse(self)</code> |  |
| [L40](../tests/test_clinical_dmplus_bootstrap_statistics.py#L40) | function/method | <code>PairedBootstrapStatisticsTests.test_t_uses_squared_errors_with_analytic_two_draw_answer(self)</code> |  |
| [L53](../tests/test_clinical_dmplus_bootstrap_statistics.py#L53) | function/method | <code>PairedBootstrapStatisticsTests.test_swapping_methods_negates_t_and_gains_but_preserves_p(self)</code> |  |
| [L60](../tests/test_clinical_dmplus_bootstrap_statistics.py#L60) | function/method | <code>PairedBootstrapStatisticsTests.test_percentile_linear_interval_is_absolute_gain_not_rmse_ci(self)</code> |  |
| [L70](../tests/test_clinical_dmplus_bootstrap_statistics.py#L70) | function/method | <code>PairedBootstrapStatisticsTests.test_zero_differences_include_equal_magnitudes_with_opposite_signs(self)</code> |  |
| [L78](../tests/test_clinical_dmplus_bootstrap_statistics.py#L78) | function/method | <code>PairedBootstrapStatisticsTests.test_constant_nonzero_difference_is_degenerate_not_p_zero(self)</code> |  |
| [L89](../tests/test_clinical_dmplus_bootstrap_statistics.py#L89) | function/method | <code>PairedBootstrapStatisticsTests.test_one_pair_has_no_t_statistic(self)</code> |  |
| [L95](../tests/test_clinical_dmplus_bootstrap_statistics.py#L95) | function/method | <code>PairedBootstrapStatisticsTests.test_pairing_uses_ids_not_order_and_does_not_mutate(self)</code> |  |
| [L104](../tests/test_clinical_dmplus_bootstrap_statistics.py#L104) | function/method | <code>PairedBootstrapStatisticsTests.test_missing_and_failed_pairs_remain_in_denominator(self)</code> |  |
| [L117](../tests/test_clinical_dmplus_bootstrap_statistics.py#L117) | function/method | <code>PairedBootstrapStatisticsTests.test_failure_on_either_side_wins_over_missing_other_side(self)</code> |  |
| [L124](../tests/test_clinical_dmplus_bootstrap_statistics.py#L124) | function/method | <code>PairedBootstrapStatisticsTests.test_default_requires_all_500_even_if_499_pairs_complete(self)</code> |  |
| [L133](../tests/test_clinical_dmplus_bootstrap_statistics.py#L133) | function/method | <code>PairedBootstrapStatisticsTests.test_reference_must_be_identical_not_merely_similar(self)</code> |  |
| [L137](../tests/test_clinical_dmplus_bootstrap_statistics.py#L137) | function/method | <code>PairedBootstrapStatisticsTests.test_pair_metadata_mismatch_or_asymmetry_rejected(self)</code> |  |
| [L147](../tests/test_clinical_dmplus_bootstrap_statistics.py#L147) | function/method | <code>PairedBootstrapStatisticsTests.test_population_task_split_seed_and_original_dm_must_match(self)</code> |  |
| [L158](../tests/test_clinical_dmplus_bootstrap_statistics.py#L158) | function/method | <code>PairedBootstrapStatisticsTests.test_failed_record_can_lack_pair_metadata_without_hiding_failure(self)</code> |  |
| [L165](../tests/test_clinical_dmplus_bootstrap_statistics.py#L165) | function/method | <code>PairedBootstrapStatisticsTests.test_invalid_records_use_shared_validator(self)</code> |  |
| [L177](../tests/test_clinical_dmplus_bootstrap_statistics.py#L177) | function/method | <code>PairedBootstrapStatisticsTests.test_invalid_planned_count_alpha_and_overflow_rejected(self)</code> |  |
| [L187](../tests/test_clinical_dmplus_bootstrap_statistics.py#L187) | function/method | <code>PairedBootstrapStatisticsTests.test_full_point_is_separate_gain_not_bootstrap_mean(self)</code> |  |
| [L197](../tests/test_clinical_dmplus_bootstrap_statistics.py#L197) | function/method | <code>PairedBootstrapStatisticsTests.test_conditional_interpretation_and_json_serialization(self)</code> |  |

<a id="module-e12f01dc791f"></a>

## tests/test_clinical_dmplus_formal.py

[Open source](../tests/test_clinical_dmplus_formal.py)

Source module docstring:

> Synthetic fixed-prefix and raw provider evidence only; no external calls.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L31](../tests/test_clinical_dmplus_formal.py#L31) | class | <code>FormalPrefixTests(unittest.TestCase)</code> |  |
| [L32](../tests/test_clinical_dmplus_formal.py#L32) | function/method | <code>FormalPrefixTests.setUp(self)</code> |  |
| [L56](../tests/test_clinical_dmplus_formal.py#L56) | function/method | <code>FormalPrefixTests.select(self, budget, split='gender', evidence=None, data=None)</code> |  |
| [L59](../tests/test_clinical_dmplus_formal.py#L59) | function/method | <code>FormalPrefixTests.test_prefix_uses_consumer_rank_not_input_order_or_request_identity(self)</code> |  |
| [L68](../tests/test_clinical_dmplus_formal.py#L68) | function/method | <code>FormalPrefixTests.test_invalid_inside_prefix_is_not_replaced_by_later_valid_row(self)</code> |  |
| [L80](../tests/test_clinical_dmplus_formal.py#L80) | function/method | <code>FormalPrefixTests.test_zero_budget_preserves_zero_denominator(self)</code> |  |
| [L86](../tests/test_clinical_dmplus_formal.py#L86) | function/method | <code>FormalPrefixTests.test_missing_model_results_do_not_become_available_valid_diagnostics(self)</code> |  |
| [L92](../tests/test_clinical_dmplus_formal.py#L92) | function/method | <code>FormalPrefixTests.test_rank_duplicates_gaps_and_bool_are_rejected(self)</code> |  |
| [L99](../tests/test_clinical_dmplus_formal.py#L99) | function/method | <code>FormalPrefixTests.test_prefix_reuses_original_training_membership_and_input_identity_checks(self)</code> |  |
| [L106](../tests/test_clinical_dmplus_formal.py#L106) | function/method | <code>FormalPrefixTests.test_unsupported_budget_never_selects_arbitrary_prefix(self)</code> |  |
| [L111](../tests/test_clinical_dmplus_formal.py#L111) | function/method | <code>FormalPrefixTests.test_cli_keeps_partial_budget_diagnostic_and_empty_validation_unestimable(self)</code> |  |
| [L169](../tests/test_clinical_dmplus_formal.py#L169) | class | <code>FormalModelEvidenceTests(unittest.TestCase)</code> |  |
| [L170](../tests/test_clinical_dmplus_formal.py#L170) | function/method | <code>FormalModelEvidenceTests.setUp(self)</code> |  |
| [L182](../tests/test_clinical_dmplus_formal.py#L182) | function/method | <code>FormalModelEvidenceTests.collect(self, run)</code> |  |
| [L185](../tests/test_clinical_dmplus_formal.py#L185) | function/method | <code>FormalModelEvidenceTests.test_complete_selected_model_does_not_wait_for_unfinished_other_model(self)</code> |  |
| [L193](../tests/test_clinical_dmplus_formal.py#L193) | function/method | <code>FormalModelEvidenceTests.test_cached_reply_uses_formal_overlap_consumers_and_counts_once(self)</code> |  |
| [L203](../tests/test_clinical_dmplus_formal.py#L203) | function/method | <code>FormalModelEvidenceTests.test_invalid_completed_responses_stay_in_full_model_denominator(self)</code> |  |
| [L210](../tests/test_clinical_dmplus_formal.py#L210) | function/method | <code>FormalModelEvidenceTests.test_selected_model_missing_result_is_rejected(self)</code> |  |
| [L215](../tests/test_clinical_dmplus_formal.py#L215) | function/method | <code>FormalModelEvidenceTests.test_modified_raw_provider_reply_is_rejected(self)</code> |  |
| [L222](../tests/test_clinical_dmplus_formal.py#L222) | function/method | <code>FormalModelEvidenceTests.test_duplicate_execution_ids_are_rejected(self)</code> |  |

<a id="module-30e2a0a81d35"></a>

## tests/test_clinical_models.py

[Open source](../tests/test_clinical_models.py)

Source module docstring:

> Synthetic checks for clinical model inputs, train-only transforms and JSON replay.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L23](../tests/test_clinical_models.py#L23) | function/method | <code>context(n)</code> |  |
| [L28](../tests/test_clinical_models.py#L28) | class | <code>ClinicalModelTests(unittest.TestCase)</code> |  |
| [L29](../tests/test_clinical_models.py#L29) | function/method | <code>ClinicalModelTests.test_training_median_population_scale_and_binary_tie_rule(self)</code> |  |
| [L48](../tests/test_clinical_models.py#L48) | function/method | <code>ClinicalModelTests.test_evaluation_cannot_fit_statistics_or_restore_omitted_columns(self)</code> |  |
| [L66](../tests/test_clinical_models.py#L66) | function/method | <code>ClinicalModelTests.test_invalid_values_rejected_even_in_omitted_features(self)</code> |  |
| [L79](../tests/test_clinical_models.py#L79) | function/method | <code>ClinicalModelTests.test_policy_binary_and_multiclass_probabilities_match_sklearn(self)</code> |  |
| [L101](../tests/test_clinical_models.py#L101) | function/method | <code>ClinicalModelTests.test_no_context_multiclass_is_exact_empirical_intercept_policy(self)</code> |  |
| [L112](../tests/test_clinical_models.py#L112) | function/method | <code>ClinicalModelTests.test_single_class_and_empty_training_are_explicit(self)</code> |  |
| [L126](../tests/test_clinical_models.py#L126) | function/method | <code>ClinicalModelTests.test_known_linear_reward_solution_and_counterfactual_action_order(self)</code> |  |
| [L144](../tests/test_clinical_models.py#L144) | function/method | <code>ClinicalModelTests.test_rank_deficiency_and_constant_action_are_recorded_without_omission(self)</code> |  |
| [L159](../tests/test_clinical_models.py#L159) | function/method | <code>ClinicalModelTests.test_reward_predictions_are_not_clipped(self)</code> |  |
| [L167](../tests/test_clinical_models.py#L167) | function/method | <code>ClinicalModelTests.test_invalid_targets_or_tasks_are_rejected(self)</code> |  |
| [L175](../tests/test_clinical_models.py#L175) | function/method | <code>ClinicalModelTests.test_convergence_warning_is_recorded_without_changing_parameters(self)</code> |  |
| [L179](../tests/test_clinical_models.py#L179) | function/method | <code>ClinicalModelTests.test_convergence_warning_is_recorded_without_changing_parameters.forced_warning(estimator, *args, **kwargs)</code> |  |
| [L192](../tests/test_clinical_models.py#L192) | function/method | <code>ClinicalModelTests.test_models_fit_independent_preprocessors_and_reject_reordered_schema(self)</code> |  |

<a id="module-f4881086c612"></a>

## tests/test_cluster_bootstrap.py

[Open source](../tests/test_cluster_bootstrap.py)

Source module docstring:

> Synthetic patient-cluster bootstrap; never fit models or query patient data.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L18](../tests/test_cluster_bootstrap.py#L18) | class | <code>SyntheticDataset()</code> |  |
| [L19](../tests/test_cluster_bootstrap.py#L19) | function/method | <code>SyntheticDataset.__init__(self, subjects=(30, 10, 30, 20, 20, 30), *, task='potassium')</code> |  |
| [L27](../tests/test_cluster_bootstrap.py#L27) | function/method | <code>SyntheticDataset.mask(self, split, role, fold=None)</code> |  |
| [L33](../tests/test_cluster_bootstrap.py#L33) | class | <code>ClusterBootstrapTests(unittest.TestCase)</code> |  |
| [L34](../tests/test_cluster_bootstrap.py#L34) | function/method | <code>ClusterBootstrapTests.population(self, dataset=None, split='gender', population='behavior_train')</code> |  |
| [L37](../tests/test_cluster_bootstrap.py#L37) | function/method | <code>ClusterBootstrapTests.test_unsorted_input_clusters_all_patient_events(self)</code> |  |
| [L45](../tests/test_cluster_bootstrap.py#L45) | function/method | <code>ClusterBootstrapTests.test_known_counts_preserve_multiplicity_and_variable_event_n(self)</code> |  |
| [L57](../tests/test_cluster_bootstrap.py#L57) | function/method | <code>ClusterBootstrapTests.test_seed_draw_reentrancy_and_call_order_independence(self)</code> |  |
| [L70](../tests/test_cluster_bootstrap.py#L70) | function/method | <code>ClusterBootstrapTests.test_population_evaluation_order_does_not_change_draw(self)</code> |  |
| [L82](../tests/test_cluster_bootstrap.py#L82) | function/method | <code>ClusterBootstrapTests.test_task_split_seed_draw_id_are_distinct_rng_keys(self)</code> |  |
| [L89](../tests/test_cluster_bootstrap.py#L89) | function/method | <code>ClusterBootstrapTests.test_only_original_selected_patients_are_drawn_with_all_events(self)</code> |  |
| [L104](../tests/test_cluster_bootstrap.py#L104) | function/method | <code>ClusterBootstrapTests.test_input_reordering_keeps_same_patient_counts(self)</code> |  |
| [L111](../tests/test_cluster_bootstrap.py#L111) | function/method | <code>ClusterBootstrapTests.test_empty_population_remains_not_estimable(self)</code> |  |
| [L123](../tests/test_cluster_bootstrap.py#L123) | function/method | <code>ClusterBootstrapTests.test_empty_dataset_is_well_defined(self)</code> |  |
| [L128](../tests/test_cluster_bootstrap.py#L128) | function/method | <code>ClusterBootstrapTests.test_no_redraw_to_recover_omitted_patient_or_rare_action(self)</code> |  |
| [L139](../tests/test_cluster_bootstrap.py#L139) | function/method | <code>ClusterBootstrapTests.test_single_patient_repeats_once_without_splitting_its_events(self)</code> |  |
| [L145](../tests/test_cluster_bootstrap.py#L145) | function/method | <code>ClusterBootstrapTests.test_invalid_draw_ids_and_seeds_fail(self)</code> |  |
| [L155](../tests/test_cluster_bootstrap.py#L155) | function/method | <code>ClusterBootstrapTests.test_invalid_counts_fail_instead_of_altering_bootstrap_n(self)</code> |  |
| [L164](../tests/test_cluster_bootstrap.py#L164) | function/method | <code>ClusterBootstrapTests.test_original_role_or_fold_leakage_is_rejected(self)</code> |  |
| [L174](../tests/test_cluster_bootstrap.py#L174) | function/method | <code>ClusterBootstrapTests.test_wrong_mask_cannot_select_other_population(self)</code> |  |
| [L180](../tests/test_cluster_bootstrap.py#L180) | function/method | <code>ClusterBootstrapTests.test_invalid_population_split_and_codes_rejected(self)</code> |  |
| [L194](../tests/test_cluster_bootstrap.py#L194) | function/method | <code>ClusterBootstrapTests.test_population_digest_binds_feature_input_and_membership(self)</code> |  |
| [L204](../tests/test_cluster_bootstrap.py#L204) | function/method | <code>ClusterBootstrapTests.test_private_counts_replay_and_metadata_are_compact_json(self)</code> |  |

<a id="module-675b36f2ff55"></a>

## tests/test_cohort_patient_splits.py

[Open source](../tests/test_cohort_patient_splits.py)

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L18](../tests/test_cohort_patient_splits.py#L18) | function/method | <code>row(event, subject, action=0, **extra)</code> |  |
| [L28](../tests/test_cohort_patient_splits.py#L28) | function/method | <code>selected(assignments, split)</code> |  |
| [L32](../tests/test_cohort_patient_splits.py#L32) | class | <code>PatientCohortSplitTests(unittest.TestCase)</code> |  |
| [L33](../tests/test_cohort_patient_splits.py#L33) | function/method | <code>PatientCohortSplitTests.test_any_high_k_patient_retains_all_low_zero_and_high_events(self)</code> |  |
| [L46](../tests/test_cohort_patient_splits.py#L46) | function/method | <code>PatientCohortSplitTests.test_sodium_threshold_and_multiple_high_values(self)</code> |  |
| [L55](../tests/test_cohort_patient_splits.py#L55) | function/method | <code>PatientCohortSplitTests.test_disease_positive_wins_unknown_negative_and_across_admissions(self)</code> |  |
| [L73](../tests/test_cohort_patient_splits.py#L73) | function/method | <code>PatientCohortSplitTests.test_gender_conflict_or_unknown_excludes_only_gender(self)</code> |  |
| [L84](../tests/test_cohort_patient_splits.py#L84) | function/method | <code>PatientCohortSplitTests.test_global_fold_matches_v1_across_tasks_and_roles(self)</code> |  |
| [L100](../tests/test_cohort_patient_splits.py#L100) | function/method | <code>PatientCohortSplitTests.test_shuffle_invariance_and_composite_admission_counts(self)</code> |  |
| [L108](../tests/test_cohort_patient_splits.py#L108) | function/method | <code>PatientCohortSplitTests.test_grouping_never_uses_outcome_values(self)</code> |  |
| [L116](../tests/test_cohort_patient_splits.py#L116) | function/method | <code>PatientCohortSplitTests.test_rejects_duplicates_ineligible_and_invalid_action_or_task(self)</code> |  |
| [L128](../tests/test_cohort_patient_splits.py#L128) | function/method | <code>PatientCohortSplitTests.test_summary_has_no_identity_strings_and_counts_conserve_events(self)</code> |  |
| [L145](../tests/test_cohort_patient_splits.py#L145) | function/method | <code>PatientCohortSplitTests.test_empty_input_and_invalid_seed(self)</code> |  |

<a id="module-532fbaae8b51"></a>

## tests/test_cohort_splits.py

[Open source](../tests/test_cohort_splits.py)

Source module docstring:

> Synthetic checks of APRIL group directions and global subject separation.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L17](../tests/test_cohort_splits.py#L17) | function/method | <code>row(event='synthetic-event', subject='synthetic-subject', action=20, **changes)</code> |  |
| [L25](../tests/test_cohort_splits.py#L25) | function/method | <code>roles(assignments, split)</code> |  |
| [L29](../tests/test_cohort_splits.py#L29) | class | <code>CohortSplitTests(unittest.TestCase)</code> |  |
| [L30](../tests/test_cohort_splits.py#L30) | function/method | <code>CohortSplitTests.test_female_to_male_and_task_specific_comorbidity_directions(self)</code> |  |
| [L44](../tests/test_cohort_splits.py#L44) | function/method | <code>CohortSplitTests.test_all_action_boundaries_including_zero_follow_declared_thresholds(self)</code> |  |
| [L58](../tests/test_cohort_splits.py#L58) | function/method | <code>CohortSplitTests.test_global_fold_is_identical_across_roles_tasks_admissions_and_order(self)</code> |  |
| [L74](../tests/test_cohort_splits.py#L74) | function/method | <code>CohortSplitTests.test_fold_does_not_depend_on_dataset_membership(self)</code> |  |
| [L82](../tests/test_cohort_splits.py#L82) | function/method | <code>CohortSplitTests.test_train_and_validation_subjects_never_overlap(self)</code> |  |
| [L99](../tests/test_cohort_splits.py#L99) | function/method | <code>CohortSplitTests.test_missing_group_flag_is_not_imputed_to_no_disease(self)</code> |  |
| [L110](../tests/test_cohort_splits.py#L110) | function/method | <code>CohortSplitTests.test_sql_boolean_spellings_and_native_flags_are_equivalent(self)</code> |  |
| [L118](../tests/test_cohort_splits.py#L118) | function/method | <code>CohortSplitTests.test_unsupported_action_task_and_ineligible_rows_are_rejected(self)</code> |  |
| [L131](../tests/test_cohort_splits.py#L131) | function/method | <code>CohortSplitTests.test_duplicate_or_missing_event_identity_is_rejected(self)</code> |  |
| [L138](../tests/test_cohort_splits.py#L138) | function/method | <code>CohortSplitTests.test_group_counts_conserve_events_and_track_action_support(self)</code> |  |
| [L156](../tests/test_cohort_splits.py#L156) | function/method | <code>CohortSplitTests.test_summary_has_no_patient_event_admission_values_and_inputs_are_unchanged(self)</code> |  |
| [L166](../tests/test_cohort_splits.py#L166) | function/method | <code>CohortSplitTests.test_empty_cohort_reports_missing_groups_without_fabricating_support(self)</code> |  |

<a id="module-56c4cbf31c2e"></a>

## tests/test_decision_features.py

[Open source](../tests/test_decision_features.py)

Source module docstring:

> Synthetic checks for clinical input/outcome separation and exact identity joins.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L11](../tests/test_decision_features.py#L11) | function/method | <code>fixture()</code> |  |
| [L29](../tests/test_decision_features.py#L29) | class | <code>DecisionFeatureTests(unittest.TestCase)</code> |  |
| [L30](../tests/test_decision_features.py#L30) | function/method | <code>DecisionFeatureTests.test_labels_actions_and_diagnoses_never_enter_feature_schema(self)</code> |  |
| [L40](../tests/test_decision_features.py#L40) | function/method | <code>DecisionFeatureTests.test_missing_values_preserved_and_counted(self)</code> |  |
| [L46](../tests/test_decision_features.py#L46) | function/method | <code>DecisionFeatureTests.test_bad_numeric_features_rejected(self)</code> |  |
| [L54](../tests/test_decision_features.py#L54) | function/method | <code>DecisionFeatureTests.test_missing_duplicate_and_wrong_identity_are_not_inner_joined_away(self)</code> |  |
| [L69](../tests/test_decision_features.py#L69) | function/method | <code>DecisionFeatureTests.test_timestamp_formatting_equivalence(self)</code> |  |
| [L74](../tests/test_decision_features.py#L74) | function/method | <code>DecisionFeatureTests.test_future_storetime_and_same_day_omr_are_rejected(self)</code> |  |
| [L86](../tests/test_decision_features.py#L86) | function/method | <code>DecisionFeatureTests.test_unverified_dictionary_cannot_be_silent_all_missing_feature(self)</code> |  |
| [L92](../tests/test_decision_features.py#L92) | function/method | <code>DecisionFeatureTests.test_render_uses_validated_identity_only(self)</code> |  |
| [L105](../tests/test_decision_features.py#L105) | function/method | <code>DecisionFeatureTests.test_render_rejects_repeated_events_or_unbounded_inputs(self)</code> |  |
| [L111](../tests/test_decision_features.py#L111) | function/method | <code>DecisionFeatureTests.test_real_query_templates_render_without_unresolved_tokens(self)</code> |  |

<a id="module-1878750957f1"></a>

## tests/test_llm_formal_summary.py

[Open source](../tests/test_llm_formal_summary.py)

Source module docstring:

> Synthetic formal/cache/raw replay only; no providers or patient data.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L27](../tests/test_llm_formal_summary.py#L27) | function/method | <code>write(path, value)</code> |  |
| [L31](../tests/test_llm_formal_summary.py#L31) | class | <code>FormalSummaryTests(unittest.TestCase)</code> |  |
| [L32](../tests/test_llm_formal_summary.py#L32) | function/method | <code>FormalSummaryTests.setUp(self)</code> |  |
| [L64](../tests/test_llm_formal_summary.py#L64) | function/method | <code>FormalSummaryTests.result(self, folder, row, *, retry=False, invalid=False)</code> |  |
| [L67](../tests/test_llm_formal_summary.py#L67) | function/method | <code>FormalSummaryTests.result.stem(number)</code> |  |
| [L69](../tests/test_llm_formal_summary.py#L69) | function/method | <code>FormalSummaryTests.result.before(number)</code> |  |
| [L73](../tests/test_llm_formal_summary.py#L73) | function/method | <code>FormalSummaryTests.result.send(request, settings, **kwargs)</code> |  |
| [L83](../tests/test_llm_formal_summary.py#L83) | function/method | <code>FormalSummaryTests.result.after(number, receipt, raw, decision)</code> |  |
| [L95](../tests/test_llm_formal_summary.py#L95) | function/method | <code>FormalSummaryTests.cache_first(self)</code> |  |
| [L107](../tests/test_llm_formal_summary.py#L107) | function/method | <code>FormalSummaryTests.build_run(self, rows=(), *, retry=False, invalid=False, active=False)</code> |  |
| [L126](../tests/test_llm_formal_summary.py#L126) | function/method | <code>FormalSummaryTests.collect(self, run=None)</code> |  |
| [L129](../tests/test_llm_formal_summary.py#L129) | function/method | <code>FormalSummaryTests.test_cache_uses_formal_consumers_and_unique_all_event_denominator(self)</code> |  |
| [L146](../tests/test_llm_formal_summary.py#L146) | function/method | <code>FormalSummaryTests.test_missing_invalid_and_short_budget_never_become_completed_500(self)</code> |  |
| [L162](../tests/test_llm_formal_summary.py#L162) | function/method | <code>FormalSummaryTests.test_retries_count_once_per_annotation_and_keep_attempt_failures(self)</code> |  |
| [L172](../tests/test_llm_formal_summary.py#L172) | function/method | <code>FormalSummaryTests.test_active_inflight_and_durable_hold_are_missing_with_distinct_counts(self)</code> |  |
| [L186](../tests/test_llm_formal_summary.py#L186) | function/method | <code>FormalSummaryTests.test_cache_and_new_duplicate_source_is_rejected(self)</code> |  |
| [L192](../tests/test_llm_formal_summary.py#L192) | function/method | <code>FormalSummaryTests.test_raw_tampering_in_new_and_cached_results_is_rejected(self)</code> |  |
| [L207](../tests/test_llm_formal_summary.py#L207) | function/method | <code>FormalSummaryTests.test_plan_partition_and_saved_cache_are_verified(self)</code> |  |
| [L222](../tests/test_llm_formal_summary.py#L222) | function/method | <code>FormalSummaryTests.test_false_complete_manifest_and_bad_rank_fail(self)</code> |  |
| [L232](../tests/test_llm_formal_summary.py#L232) | function/method | <code>FormalSummaryTests.test_execution_source_change_is_rejected_before_collection(self)</code> |  |
| [L241](../tests/test_llm_formal_summary.py#L241) | function/method | <code>FormalSummaryTests.test_outputs_private_hashed_and_no_overwrite(self)</code> |  |
| [L257](../tests/test_llm_formal_summary.py#L257) | function/method | <code>FormalSummaryTests.test_cli_only_emits_aggregate_counts_and_paths(self)</code> |  |

<a id="module-d1b73e75fd32"></a>

## tests/test_llm_run_summary.py

[Open source](../tests/test_llm_run_summary.py)

Source module docstring:

> Synthetic receipts only: no clinical rows, credentials, or network access.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L25](../tests/test_llm_run_summary.py#L25) | function/method | <code>write(path, value)</code> |  |
| [L29](../tests/test_llm_run_summary.py#L29) | class | <code>RunSummaryTests(unittest.TestCase)</code> |  |
| [L30](../tests/test_llm_run_summary.py#L30) | function/method | <code>RunSummaryTests.setUp(self)</code> |  |
| [L36](../tests/test_llm_run_summary.py#L36) | function/method | <code>RunSummaryTests.make_packet(self, task)</code> |  |
| [L66](../tests/test_llm_run_summary.py#L66) | function/method | <code>RunSummaryTests.make_run(self, name, rows=None, *, packet=None, retry_first=False, malformed=False, complete=True)</code> |  |
| [L78](../tests/test_llm_run_summary.py#L78) | function/method | <code>RunSummaryTests.make_run.send(record, settings, **kwargs)</code> |  |
| [L91](../tests/test_llm_run_summary.py#L91) | function/method | <code>RunSummaryTests.make_run.stem(number)</code> |  |
| [L93](../tests/test_llm_run_summary.py#L93) | function/method | <code>RunSummaryTests.make_run.before(number)</code> |  |
| [L96](../tests/test_llm_run_summary.py#L96) | function/method | <code>RunSummaryTests.make_run.after(number, receipt, raw, decision)</code> |  |
| [L115](../tests/test_llm_run_summary.py#L115) | function/method | <code>RunSummaryTests.collect(self, *runs)</code> |  |
| [L118](../tests/test_llm_run_summary.py#L118) | function/method | <code>RunSummaryTests.rebind_receipt(self, run, result)</code> |  |
| [L124](../tests/test_llm_run_summary.py#L124) | function/method | <code>RunSummaryTests.test_disjoint_warmup_and_remaining_runs_have_unique_event_metrics(self)</code> |  |
| [L142](../tests/test_llm_run_summary.py#L142) | function/method | <code>RunSummaryTests.test_retry_attempts_do_not_duplicate_annotations_or_tokens(self)</code> |  |
| [L152](../tests/test_llm_run_summary.py#L152) | function/method | <code>RunSummaryTests.test_missing_and_invalid_remain_in_factual_denominator(self)</code> |  |
| [L164](../tests/test_llm_run_summary.py#L164) | function/method | <code>RunSummaryTests.test_interrupted_run_preserves_saved_results_and_missing(self)</code> |  |
| [L176](../tests/test_llm_run_summary.py#L176) | function/method | <code>RunSummaryTests.test_duplicate_runs_requests_and_packets_are_rejected(self)</code> |  |
| [L184](../tests/test_llm_run_summary.py#L184) | function/method | <code>RunSummaryTests.test_packet_hash_label_identity_and_plan_binding_are_validated(self)</code> |  |
| [L198](../tests/test_llm_run_summary.py#L198) | function/method | <code>RunSummaryTests.test_raw_and_receipt_tampering_is_rejected(self)</code> |  |
| [L211](../tests/test_llm_run_summary.py#L211) | function/method | <code>RunSummaryTests.test_rehashed_forged_prediction_is_rejected_by_raw_renormalization(self)</code> |  |
| [L224](../tests/test_llm_run_summary.py#L224) | function/method | <code>RunSummaryTests.test_path_traversal_and_attempt_count_mismatch_are_rejected(self)</code> |  |
| [L237](../tests/test_llm_run_summary.py#L237) | function/method | <code>RunSummaryTests.test_both_tasks_are_separate_and_cf_never_enters_factual_metrics(self)</code> |  |
| [L247](../tests/test_llm_run_summary.py#L247) | function/method | <code>RunSummaryTests.test_private_outputs_hashes_and_no_overwrite(self)</code> |  |
| [L262](../tests/test_llm_run_summary.py#L262) | function/method | <code>RunSummaryTests.test_cli_prints_only_aggregate_counts_and_paths(self)</code> |  |

<a id="module-0f1dce581793"></a>

## tests/test_outcomes.py

[Open source](../tests/test_outcomes.py)

Source module docstring:

> Synthetic boundary tests for the proposed D003 potassium outcome oracle.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L18](../tests/test_outcomes.py#L18) | function/method | <code>lab(hours: float, value: object=4.0, *, itemid: int=50971, unit: object='mEq/L', stored_after_hours: float &#124; None=0.25, source_id: object=None) -&gt; PotassiumLabRow</code> |  |
| [L43](../tests/test_outcomes.py#L43) | class | <code>ProposedPotassiumOutcomeTests(unittest.TestCase)</code> |  |
| [L44](../tests/test_outcomes.py#L44) | function/method | <code>ProposedPotassiumOutcomeTests.test_open_anchor_closed_24_hour_window_and_supported_items(self)</code> |  |
| [L65](../tests/test_outcomes.py#L65) | function/method | <code>ProposedPotassiumOutcomeTests.test_first_timestamp_is_chosen_before_quality_and_never_skipped(self)</code> |  |
| [L78](../tests/test_outcomes.py#L78) | function/method | <code>ProposedPotassiumOutcomeTests.test_same_time_duplicates_and_quality_siblings_are_retained(self)</code> |  |
| [L95](../tests/test_outcomes.py#L95) | function/method | <code>ProposedPotassiumOutcomeTests.test_conflicting_supported_values_exclude_the_whole_group(self)</code> |  |
| [L104](../tests/test_outcomes.py#L104) | function/method | <code>ProposedPotassiumOutcomeTests.test_any_finite_unrecognized_unit_excludes_without_conversion(self)</code> |  |
| [L124](../tests/test_outcomes.py#L124) | function/method | <code>ProposedPotassiumOutcomeTests.test_storetime_does_not_select_but_reversed_nonmissing_time_excludes(self)</code> |  |
| [L144](../tests/test_outcomes.py#L144) | function/method | <code>ProposedPotassiumOutcomeTests.test_additional_treatment_interval_has_open_start_and_closed_end(self)</code> |  |
| [L170](../tests/test_outcomes.py#L170) | function/method | <code>ProposedPotassiumOutcomeTests.test_same_anchor_distinct_event_requires_episode_rule_and_excludes(self)</code> |  |
| [L183](../tests/test_outcomes.py#L183) | function/method | <code>ProposedPotassiumOutcomeTests.test_input_order_and_source_ids_cannot_change_scientific_result(self)</code> |  |
| [L199](../tests/test_outcomes.py#L199) | function/method | <code>ProposedPotassiumOutcomeTests.test_result_explicitly_remains_a_proposal_and_ignores_proxy_target(self)</code> |  |
| [L206](../tests/test_outcomes.py#L206) | function/method | <code>ProposedPotassiumOutcomeTests.test_malformed_times_and_rows_are_rejected(self)</code> |  |

<a id="module-bd129354456e"></a>

## tests/test_run_reproduction.py

[Open source](../tests/test_run_reproduction.py)

Source module docstring:

> Synthetic integrity tests for the portable adapter; no MIMIC records.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L13](../tests/test_run_reproduction.py#L13) | class | <code>AdapterIntegrityTests(unittest.TestCase)</code> |  |
| [L14](../tests/test_run_reproduction.py#L14) | function/method | <code>AdapterIntegrityTests.test_relative_paths_block_traversal_absolute_and_external_symlink(self)</code> |  |
| [L22](../tests/test_run_reproduction.py#L22) | function/method | <code>AdapterIntegrityTests.test_committed_pair_rejects_wrong_run_identity(self)</code> |  |
| [L30](../tests/test_run_reproduction.py#L30) | function/method | <code>AdapterIntegrityTests.test_committed_result_corruption_rejected(self)</code> |  |
| [L37](../tests/test_run_reproduction.py#L37) | function/method | <code>AdapterIntegrityTests.test_committed_model_corruption_rejected(self)</code> |  |
| [L44](../tests/test_run_reproduction.py#L44) | function/method | <code>AdapterIntegrityTests.test_committed_draw_cannot_be_overwritten(self)</code> |  |
| [L50](../tests/test_run_reproduction.py#L50) | function/method | <code>AdapterIntegrityTests.test_selection_rejects_repeated_and_out_of_range_ids(self)</code> |  |
| [L55](../tests/test_run_reproduction.py#L55) | function/method | <code>AdapterIntegrityTests.test_numerical_comparison_preserves_declared_tolerance(self)</code> |  |

<a id="module-1053c15840e5"></a>

## tests/test_science.py

[Open source](../tests/test_science.py)

Source module docstring:

> Hand-calculated scientific invariants, independent of model training.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L11](../tests/test_science.py#L11) | class | <code>RewardTests(unittest.TestCase)</code> |  |
| [L12](../tests/test_science.py#L12) | function/method | <code>RewardTests.test_reference_ranges_and_published_scale(self)</code> |  |
| [L28](../tests/test_science.py#L28) | function/method | <code>RewardTests.test_all_f1_boundaries_are_left_closed(self)</code> |  |
| [L39](../tests/test_science.py#L39) | function/method | <code>RewardTests.test_invalid_lab_task_and_scale(self)</code> |  |
| [L53](../tests/test_science.py#L53) | class | <code>MetricTests(unittest.TestCase)</code> |  |
| [L54](../tests/test_science.py#L54) | function/method | <code>MetricTests.test_f1_by_hand_and_missing_classes(self)</code> |  |
| [L64](../tests/test_science.py#L64) | function/method | <code>MetricTests.test_rmse_is_not_mean_absolute_error_and_bias_keeps_sign(self)</code> |  |
| [L72](../tests/test_science.py#L72) | function/method | <code>MetricTests.test_entropy_by_hand_and_full_action_spaces(self)</code> |  |
| [L80](../tests/test_science.py#L80) | function/method | <code>MetricTests.test_invalid_metric_inputs(self)</code> |  |
| [L97](../tests/test_science.py#L97) | class | <code>DirectMethodTests(unittest.TestCase)</code> |  |
| [L98](../tests/test_science.py#L98) | function/method | <code>DirectMethodTests.test_stochastic_and_deterministic_policies_by_hand(self)</code> |  |
| [L105](../tests/test_science.py#L105) | function/method | <code>DirectMethodTests.test_unclipped_values_and_zero_mass_context(self)</code> |  |
| [L109](../tests/test_science.py#L109) | function/method | <code>DirectMethodTests.test_shape_probability_and_finite_validation(self)</code> |  |

<a id="module-996a7bd873d5"></a>

## tests/test_units.py

[Open source](../tests/test_units.py)

Source module docstring:

> Synthetic physical-unit checks; no clinical cohort or dosing advice.

| Source | Kind | Signature | Existing docstring |
|---|---|---|---|
| [L7](../tests/test_units.py#L7) | class | <code>SalineUnitTests(unittest.TestCase)</code> |  |
| [L8](../tests/test_units.py#L8) | function/method | <code>SalineUnitTests.test_label_concentration_and_volume_scaling(self)</code> |  |
| [L15](../tests/test_units.py#L15) | function/method | <code>SalineUnitTests.test_milliliters_are_not_copied_or_binned_as_actions(self)</code> |  |
| [L20](../tests/test_units.py#L20) | function/method | <code>SalineUnitTests.test_invalid_or_ambiguous_source_amounts_fail(self)</code> |  |
