# LLM annotation code

[Back to the code navigation guide](CODE_GUIDE.md).


The five LLMs are remote API services. This repository contains their request adapters, prompts, response parser, execution bookkeeping, and cached-result consumers; it does not contain their neural-network architectures or local weight checkpoints. They supply predicted post-treatment laboratory values. The locally fitted DM and DM+ reward regressions are different models, implemented in the clinical OPE modules.

All five API adapters share one implementation: [`src/april_repro/llm_five_requests.py`](../src/april_repro/llm_five_requests.py). There are no separate `deepseek.py`, `qwen.py`, or `kimi.py` training files.

### Model identifiers recorded for these experiments

These are the identifiers in the checked-in experiment configuration, not a fresh check of current provider availability.

| Model key used by the code | Recorded API model ID | Provider | Where to inspect |
|---|---|---|---|
| `gpt-4o-mini` | `gpt-4o-mini-2024-07-18` | OpenAI | `MODEL_REGISTRY["gpt-4o-mini"]`; `[models.gpt-4o-mini]` |
| `o3-mini` | `o3-mini-2025-01-31` | OpenAI | `MODEL_REGISTRY["o3-mini"]`; `[models.o3-mini]` |
| `kimi` | `kimi-k2.6` | Moonshot | `MODEL_REGISTRY["kimi"]`; `[models.kimi]` |
| `deepseek` | `deepseek-flash` | DeepSeek | `MODEL_REGISTRY["deepseek"]`; `[models.deepseek]` |
| `qwen` | `qwen3.7-plus-2026-05-26` | Alibaba | `QWEN_DOMESTIC_MODEL_REGISTRY["qwen"]`; `[models.qwen]` |

The formal experiment uses [`config/llm-five-models-qwen-domestic.toml`](../config/llm-five-models-qwen-domestic.toml). Its Qwen endpoint is `https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions`. [`config/llm-five-models.toml`](../config/llm-five-models.toml) records the separate international adapter profile. They are not interchangeable: `llm_formal_plan.load_config()` explicitly requires the domestic profile for the historical formal plan.

The executed registry is defined in Python and validated against the TOML by `validate_five_config()`. Changing a model ID only in TOML will fail validation; a new experiment must update the registry/profile consistently and create new request identities. This avoids silently treating a replacement model as a reproduction of an old run.

`config/llm-two-openai.toml` contains the common prompt/selection protocol inherited from the initial two-OpenAI pilot. `config/llm-formal-main.toml` sets the formal 500 factual / 500 counterfactual selections and the `[0, 100, 200, 300, 400, 500]` annotation budgets. The 500 factual count is a local evaluation choice; the counterfactual count corresponds to the paper comparison.

### Read the code in this order

| Stage | File and entry function | What it does |
|---|---|---|
| Select event/action pairs | [`llm_packet.py:97`](../src/april_repro/llm_packet.py#L97), `select_pairs()` | Selects deterministic event/action prefixes separately for task, split, and factual/counterfactual mode. Factual pairs come from behavior validation; counterfactual pairs from behavior training. Selection uses hashes, not outcomes or model predictions. |
| Construct the clinical prompt | [`llm_requests.py:162`](../src/april_repro/llm_requests.py#L162), `render_prompt()` | Inserts the declared 15 pretreatment features, latest electrolyte, specified dose, and relative prediction time into `PROMPT_TEMPLATE`. Missing values remain `unknown`. |
| Construct a base request | [`llm_requests.py:210`](../src/april_repro/llm_requests.py#L210), `build_request()` | Binds event/task/action/model identity to the prompt and creates separate API payload and private metadata. Does not make a network call. |
| Adapt to one of five LLMs | [`llm_five_requests.py:205`](../src/april_repro/llm_five_requests.py#L205), `build_five_request()` | Reuses the prompt verbatim and applies the selected model, endpoint, allowed response model IDs, and fixed API parameters. |
| Freeze a formal annotation plan | [`llm_formal_plan.py:186`](../src/april_repro/llm_formal_plan.py#L186), `prepare_formal_plan()` | Combines deterministic selections for one or both tasks, deduplicates requests across consumers, validates reusable pilot annotations, and writes immutable request/label files plus a manifest. No API calls. |
| Load and verify the plan | [`llm_formal_run.py:91`](../src/april_repro/llm_formal_run.py#L91), `load_formal_plan()` | Rechecks manifests, requests, factual labels, and cache bindings before execution/summary. |
| Execute new annotations | [`llm_formal_run.py:329`](../src/april_repro/llm_formal_run.py#L329), `run_formal_plan()` | Executes new requests with per-model workers, persistent attempts, cache reuse, locking, and resume checks. This is a library function, not a standalone command-line script in this repository. |
| Send one HTTP request | [`llm_transport.py:86`](../src/april_repro/llm_transport.py#L86), `execute_once()` | Checks `preflight()`, sends only `record["payload"]`, and returns normalized receipt plus original response bytes. No automatic model substitution or region fallback. |
| Decide and perform retries | [`llm_retries.py:51`](../src/april_repro/llm_retries.py#L51), `retry_decision()`; [`:89`](../src/april_repro/llm_retries.py#L89), `execute_with_retries()` | Retries eligible transient transport/service failures at most twice, preserves every attempt, and does not retry a completed answer merely because its content was invalid. |
| Validate the API response envelope | [`llm_receipts.py:120`](../src/april_repro/llm_receipts.py#L120), `normalize_receipt()` | Verifies HTTP status, response model, a single completed assistant choice, and absence of refusal/tool call before parsing the answer. |
| Parse a lab prediction and map reward | [`llm_predictions.py:77`](../src/april_repro/llm_predictions.py#L77), `parse_prediction_response()` | Requires exactly `predicted_lab_value` and `justification`; checks finite positive numeric prediction; computes fixed reward and F1 class via `rewards.py`. Invalid outputs remain invalid, never replaced by normal/zero values. |
| Build factual evaluation records | [`llm_receipts.py:197`](../src/april_repro/llm_receipts.py#L197), `factual_record_from_receipt()` | Joins observed post-treatment labels locally for evaluation, after the API call. Labels are not part of the prompt. |
| Compute factual prediction metrics | [`llm_predictions.py:195`](../src/april_repro/llm_predictions.py#L195), `evaluate_factual_predictions()` | Reports weighted F1, lab MAE/RMSE, confusion matrix, and coverage. Invalid/missing predictions remain in the coverage denominator; numerical metrics use valid predictions only. Lab RMSE here is not OPE RMSE. |
| Collect a complete formal run | [`llm_formal_summary.py:167`](../src/april_repro/llm_formal_summary.py#L167), `summarize_formal_run()`; [`:257`](../src/april_repro/llm_formal_summary.py#L257), `write_summary()` | Revalidates cached/new receipts, creates parsed annotation rows, groups by model/task/split, computes factual metrics and budget-prefix coverage, then writes the summary. Does not fit DM+. |

The numerical mapping lives in [`rewards.py:43`](../src/april_repro/rewards.py#L43), `reward_from_lab()`, and [`rewards.py:67`](../src/april_repro/rewards.py#L67), `bin_lab_value()`. The metric implementation is [`metrics.py:15`](../src/april_repro/metrics.py#L15), `weighted_f1()`. Reward intervals and F1 bins are separate definitions.

### Which LLM-related files can actually be run?

The delivered repository exposes these offline summary scripts:

```bash
python scripts/summarize_formal_llm_run.py --help
python scripts/summarize_five_llm_runs.py --help
```

For a complete formal plan and its raw run directory, the formal summary command is:

```bash
python scripts/summarize_formal_llm_run.py \
  --plan-directory /path/to/formal-plan \
  --run-directory /path/to/formal-run \
  --output-directory /path/to/new-summary
```

The output directory must be new. This command revalidates local annotation records and computes factual metrics; it sends no API requests. It requires the bound plan, labels, run receipts, and any referenced pilot evidence. An aggregate report CSV is not a substitute for these inputs. The selected-baseline release is intended for the packaged baseline workflow; do not assume it is a full five-provider raw annotation archive.

The pilot counterpart accepts repeated `--packet-directory` and `--run-directory` arguments. Its implementation is `llm_run_summary.summarize_runs()` / `write_summary()`.

There is currently no checked-in `scripts/run_formal_llm_plan.py` or `scripts/prepare_formal_llm_plan.py` launcher in this repository. The implementation functions are present, but running `python -m april_repro.llm_formal_run` is not a command to launch an annotation job. For the delivered baseline reproduction, use the repository's `run_reproduction.py` interface and cached annotations; fresh API annotation is a separate workflow requiring a new explicit wrapper/configuration and the inputs above.

`python -m april_repro ...` and the installed `april-repro` command both route to [`cli.py:242`](../src/april_repro/cli.py#L242), `main()`. That CLI only provides `doctor`, `protocol check`, and read-only `db check`, `db inspect`, `db profile`; it does not run LLM annotation, fit DM/DM+, or draw figures.

### Other LLM files and when to read them

| File | Main functions | Why it exists |
|---|---|---|
| `llm_packet.py` | `load_config()`, `prepare_packet()` | Initial local two-OpenAI pilot packet and integrity metadata. |
| `llm_five_packet.py` | `prepare_five_packet()` | Converts the validated initial packet into the five-provider request profile without API calls. |
| `llm_run_summary.py` | `summarize_runs()`, `write_summary()` | Pilot collection, receipt validation, coverage, and factual metrics. |
| `llm_credentials.py` | `load_provider_env()` | Reads only named provider variables from a selected dotenv file without executing shell code. It contains loader code, not API keys. Cached reproduction does not need provider keys. |
| `llm_transport.py` | `preflight()` | Checks the explicitly configured endpoint, recorded account-handling flags, API-key presence, and the registry's recorded shutdown date. It does not probe current account access. In particular, the checked-in `o3-mini` shutdown date causes this local preflight to block new execution from that date; cached results remain reproducible. |
| `llm_formal_run.py` | `verify_request_result()`, `inspect_request()`, `exclusive_run_lock()` | Validates completed attempts and prevents duplicate/ambiguous resume execution. |
| `llm_formal_recovery.py` | `verify_recovery_provenance()`, `run_recovery()` | Earlier provenance-preserving recovery implementation. Read to audit earlier recovery segments, not as the default baseline runner. |
| `llm_formal_recovery_v2.py` | `verify_recovery_provenance()`, `run_recovery()` | Later recorded recovery implementation with its own provenance version. Recovery is distinct from recomputing cached OPE results. |

`config/llm-runtime.example.toml` is a template for actual provider/account settings. Its default flags are false and it contains no credentials. These settings are consumed by transport when a fresh request is sent, not by cached statistical reproduction.

### Files produced by the annotation pipeline

| Producer | Output | Meaning |
|---|---|---|
| `prepare_formal_plan()` | `requests.jsonl` | Frozen request records, payloads, hashes, and consumer ranks. |
| `prepare_formal_plan()` | `factual-labels.jsonl` | Local observed labels for factual evaluation; not API payloads. |
| `prepare_formal_plan()` | `manifest.json` | Plan configuration, selection counts, source identities, and output hashes. |
| `run_formal_plan()` | `plan.json`, `status.json`, `manifest.json` | Execution binding, progress, and completion metadata. |
| `run_formal_plan()` | `requests/<model-key>/<request-id>...` | Started-attempt records, original response bytes, normalized receipts, final annotation decisions, and held-state records. |
| `llm_formal_summary.write_summary()` | `parsed-annotations.jsonl` | Parsed lab predictions/rewards with model, event/action, split consumers, and validity. This is the bridge from the LLM stage to the DM+ stage. |
| `llm_formal_summary.write_summary()` | `summary.json`, `manifest.json` | Factual metrics, coverage, budget availability, and file integrity. |

The first useful reading path is: `llm_requests.render_prompt()` → `llm_five_requests.build_five_request()` → `llm_predictions.parse_prediction_response()` → `rewards.reward_from_lab()` → the DM+ fitting code. Read transport/recovery internals later if the task is changing model integration or auditing a failed API job.
