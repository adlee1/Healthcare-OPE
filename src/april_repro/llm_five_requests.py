"""Fixed five-provider adapters for existing APRIL prompts; no network access.

The three additional providers are a user-selected adapted replication, not the
paper's historical model set. Only ``payload`` is sent; identity and transport
provenance remain in the private ledger. Endpoint selection never falls back to
another region. Provider names/aliases do not establish account availability.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import tomllib

from april_repro.cohort_splits import ACTIONS
from april_repro.llm_requests import MODEL_SPECS, PROTOCOL_ID, PROTOCOL_VERSION


REGISTRY_VERSION = "april-five-model-adapters-v1"
MODEL_REGISTRY = {
    "gpt-4o-mini": {
        "provider": "openai", "model": "gpt-4o-mini-2024-07-18",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
        "accepted_response_models": ["gpt-4o-mini-2024-07-18"],
        "model_version_kind": "dated_snapshot",
        "parameters": {"temperature": 0, "max_completion_tokens": 4096, "store": False},
        "shutdown_date": "2027-01-14", "account_access_verified": False,
        "sources": ["https://developers.openai.com/api/docs/deprecations"],
    },
    "o3-mini": {
        "provider": "openai", "model": "o3-mini-2025-01-31",
        "endpoint": "https://api.openai.com/v1/chat/completions",
        "api_key_env": "OPENAI_API_KEY",
        "accepted_response_models": ["o3-mini-2025-01-31"],
        "model_version_kind": "dated_snapshot",
        "parameters": {"max_completion_tokens": 4096, "store": False},
        "shutdown_date": "2026-10-23", "account_access_verified": False,
        "sources": ["https://developers.openai.com/api/docs/deprecations"],
    },
    "kimi": {
        "provider": "moonshot", "model": "kimi-k2.6",
        "endpoint": "https://api.moonshot.cn/v1/chat/completions",
        "api_key_env": "MOONSHOT_API_KEY",
        "accepted_response_models": ["kimi-k2.6"],
        "model_version_kind": "versioned_model_id_not_immutable",
        "parameters": {"max_tokens": 4096, "thinking": {"type": "disabled"}},
        "shutdown_date": None, "account_access_verified": False,
        "effective_temperature": 0.6,
        "temperature_note": "Service fixes non-thinking temperature to 0.6; omit parameter.",
        "sources": ["https://platform.kimi.com/docs/api/models-overview",
                    "https://platform.kimi.com/docs/guide/kimi-k2-6-quickstart"],
    },
    "deepseek": {
        "provider": "deepseek", "model": "deepseek-flash",
        "endpoint": "https://api.deepseek.com/chat/completions",
        "api_key_env": "DEEPSEEK_API_KEY",
        "accepted_response_models": ["deepseek-flash"],
        "model_version_kind": "rolling_alias",
        "parameters": {"temperature": 0, "max_tokens": 4096,
                       "thinking": {"type": "disabled"}},
        "shutdown_date": None, "account_access_verified": False,
        "documented_served_model": "DeepSeek-V4.1-Flash-1017",
        "sources": ["https://api-docs.deepseek.com/quick_start/pricing/",
                    "https://api-docs.deepseek.com/api/create-chat-completion/"],
    },
    "qwen": {
        "provider": "alibaba", "model": "qwen3.7-plus-2026-05-26",
        "endpoint": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions",
        "api_key_env": "DASHSCOPE_API_KEY",
        "accepted_response_models": ["qwen3.7-plus-2026-05-26"],
        "model_version_kind": "dated_snapshot",
        "parameters": {"temperature": 0, "max_completion_tokens": 4096,
                       "enable_thinking": False},
        "shutdown_date": None, "account_access_verified": False,
        "region_note": "International endpoint fixed; account and workspace region unverified.",
        "sources": ["https://www.alibabacloud.com/help/en/model-studio/qwen3-7-plus",
                    "https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions"],
    },
}


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()


REGISTRY_SHA256 = _sha(MODEL_REGISTRY)
# Preserve the original registry byte-for-byte as the default. A different
# region is an explicit, separately hashed profile, never a runtime fallback.
QWEN_DOMESTIC_REGISTRY_VERSION = "april-five-model-adapters-qwen-domestic-v1"
QWEN_DOMESTIC_MODEL_REGISTRY = deepcopy(MODEL_REGISTRY)
QWEN_DOMESTIC_MODEL_REGISTRY["qwen"].update(
    endpoint="https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions",
    region_note="Mainland China endpoint explicitly selected; no international fallback.",
    sources=["https://platform.qianwenai.com/docs/api-reference/chat/openai-chat",
             "https://help.aliyun.com/zh/model-studio/qwen3-7-plus"],
)
MODEL_REGISTRIES = {
    REGISTRY_VERSION: MODEL_REGISTRY,
    QWEN_DOMESTIC_REGISTRY_VERSION: QWEN_DOMESTIC_MODEL_REGISTRY,
}
REGISTRY_HASHES = {version: _sha(registry) for version, registry in MODEL_REGISTRIES.items()}


def _registry(version):
    if not isinstance(version, str) or version not in MODEL_REGISTRIES:
        raise ValueError("Unknown registry version")
    return MODEL_REGISTRIES[version], REGISTRY_HASHES[version]


_TRANSPORT_FIELDS = ("provider", "endpoint", "api_key_env", "accepted_response_models",
                     "model_version_kind")
_BASE_FIELDS = {"request_id", "cache_key", "protocol_version", "protocol_id",
                "prompt_sha256", "payload_sha256", "metadata", "payload"}
_IDENTITY_FIELDS = {"event_id", "input_manifest_sha256", "mode", "task", "observed_action",
                    "action", "model_key", "model_snapshot", "historical_snapshot_recovered"}


def _hash_value(value):
    return isinstance(value, str) and re.fullmatch("[0-9a-f]{64}", value) is not None


def _same(actual, expected, message):
    # Canonical JSON also distinguishes booleans from numbers and rejects NaN.
    if _sha(actual) != _sha(expected):
        raise ValueError(message)


def _check_common(record, *, five):
    if not isinstance(record, dict):
        raise ValueError("Request must be a dictionary")
    fields = _BASE_FIELDS | ({"registry_version", "registry_sha256", "transport",
                             "transport_sha256"} if five else set())
    if set(record) not in (fields, fields | {"consumers"}):
        raise ValueError("Unexpected or missing request fields")
    if record["protocol_version"] != PROTOCOL_VERSION or record["protocol_id"] != PROTOCOL_ID:
        raise ValueError("Unknown prompt protocol")
    metadata = record["metadata"]
    required = _IDENTITY_FIELDS | ({"provider"} if five else set())
    if not isinstance(metadata, dict) or set(metadata) != required:
        raise ValueError("Unexpected or missing private metadata")
    if not all(_hash_value(metadata[key]) for key in ("event_id", "input_manifest_sha256")):
        raise ValueError("Invalid private identity hash")
    task = metadata["task"]
    if not isinstance(task, str) or task not in ACTIONS:
        raise ValueError("Unknown electrolyte task")
    for key in ("action", "observed_action"):
        if type(metadata[key]) is not int or metadata[key] not in ACTIONS[task]:
            raise ValueError("Invalid discrete action")
    mode = metadata["mode"]
    if mode not in ("factual", "counterfactual") or ((mode == "factual") !=
            (metadata["action"] == metadata["observed_action"])):
        raise ValueError("Inconsistent annotation mode and actions")
    if metadata["historical_snapshot_recovered"] is not False:
        raise ValueError("Historical snapshot recovery must not be claimed")
    payload = record["payload"]
    messages = payload.get("messages") if isinstance(payload, dict) else None
    if (not isinstance(messages, list) or len(messages) != 1 or
            not isinstance(messages[0], dict) or set(messages[0]) != {"role", "content"} or
            messages[0]["role"] != "user" or not isinstance(messages[0]["content"], str) or
            not messages[0]["content"]):
        raise ValueError("Expected one nonempty user prompt")
    if hashlib.sha256(messages[0]["content"].encode()).hexdigest() != record["prompt_sha256"]:
        raise ValueError("Prompt hash mismatch")
    if _sha(payload) != record["payload_sha256"]:
        raise ValueError("Payload hash mismatch")
    if "consumers" in record:
        consumers = record["consumers"]
        if not isinstance(consumers, list) or not consumers:
            raise ValueError("Consumers must be a nonempty list when present")
        for consumer in consumers:
            if (not isinstance(consumer, dict) or set(consumer) != {"split", "mode", "fold", "rank"}
                    or consumer["split"] not in ("gender", "comorbidity", "dosage")
                    or consumer["mode"] != mode or consumer["fold"] !=
                    ("validation" if mode == "factual" else "train")
                    or type(consumer["rank"]) is not int or consumer["rank"] < 1):
                raise ValueError("Invalid request consumer")
    return metadata, payload


def validate_base_request(record):
    """Verify an old two-OpenAI request without reading its patient source files."""
    metadata, payload = _check_common(record, five=False)
    key = metadata["model_key"]
    if not isinstance(key, str) or key not in MODEL_SPECS:
        raise ValueError("Unknown base model")
    if metadata["model_snapshot"] != MODEL_SPECS[key]["model"]:
        raise ValueError("Base model identity mismatch")
    _same(payload, {**MODEL_SPECS[key], "messages": payload["messages"]},
          "Base model parameter mismatch")
    identity = {"metadata": metadata, "protocol_id": PROTOCOL_ID,
                "payload_sha256": record["payload_sha256"]}
    if record["request_id"] != _sha(identity) or record["cache_key"] != record["request_id"]:
        raise ValueError("Base request identity mismatch")


def _request_identity(record):
    return {key: record[key] for key in ("metadata", "protocol_id", "payload_sha256",
                                        "registry_version", "registry_sha256", "transport_sha256")}


def build_five_request(base_record, model_key, *, registry_version=REGISTRY_VERSION):
    """Reuse the verified prompt verbatim; bind provider routing and parameters.

    The same event/action/prompt yields the same new request regardless of which
    old OpenAI model record supplied it. Consumers do not alter API/cache identity.
    """
    validate_base_request(base_record)
    registry, registry_sha = _registry(registry_version)
    if not isinstance(model_key, str) or model_key not in registry:
        raise ValueError("Unknown five-provider model")
    spec = registry[model_key]
    metadata = deepcopy(base_record["metadata"])
    metadata.update(model_key=model_key, model_snapshot=spec["model"], provider=spec["provider"])
    payload = {"model": spec["model"], **deepcopy(spec["parameters"]),
               "messages": deepcopy(base_record["payload"]["messages"])}
    transport = {key: deepcopy(spec[key]) for key in _TRANSPORT_FIELDS}
    result = {
        "protocol_version": PROTOCOL_VERSION, "protocol_id": PROTOCOL_ID,
        "prompt_sha256": base_record["prompt_sha256"], "payload_sha256": _sha(payload),
        "metadata": metadata, "payload": payload, "registry_version": registry_version,
        "registry_sha256": registry_sha, "transport": transport,
        "transport_sha256": _sha(transport),
    }
    result["request_id"] = result["cache_key"] = _sha(_request_identity(result))
    if "consumers" in base_record:
        result["consumers"] = deepcopy(base_record["consumers"])
    validate_request(result)
    return result


def validate_request(record):
    """Reject routing/parameter/identity drift before any transport operation."""
    metadata, payload = _check_common(record, five=True)
    registry, registry_sha = _registry(record["registry_version"])
    key = metadata["model_key"]
    if not isinstance(key, str) or key not in registry:
        raise ValueError("Unknown five-provider model")
    spec = registry[key]
    if metadata["provider"] != spec["provider"] or metadata["model_snapshot"] != spec["model"]:
        raise ValueError("Provider/model metadata mismatch")
    if record["registry_sha256"] != registry_sha:
        raise ValueError("Registry version mismatch")
    _same(payload, {"model": spec["model"], **spec["parameters"], "messages": payload["messages"]},
          "Fixed provider parameter mismatch")
    _same(record["transport"], {key: spec[key] for key in _TRANSPORT_FIELDS},
          "Fixed transport mismatch")
    if record["transport_sha256"] != _sha(record["transport"]):
        raise ValueError("Transport hash mismatch")
    if record["request_id"] != _sha(_request_identity(record)) or record["cache_key"] != record["request_id"]:
        raise ValueError("Request identity mismatch")


def validate_five_config(path):
    """Check the small offline config against the executed registry, not prose."""
    path = Path(path).resolve()
    raw = path.read_bytes()
    config = tomllib.loads(raw.decode("utf-8"))
    registry_version = config.get("registry_version")
    registry, registry_sha = _registry(registry_version)
    effective = {"model_keys": list(registry), "scope": "offline_review_pilot",
                 "network_calls": False, "status": "adapters_only",
                 "registry_version": registry_version, "registry_sha256": registry_sha}
    for key in ("model_keys", "scope", "network_calls", "status", "registry_version"):
        _same(config.get(key), effective[key], "Five-model configuration mismatch: " + key)
    models = config.get("models")
    if not isinstance(models, dict) or set(models) != set(registry):
        raise ValueError("Configuration must declare exactly the five models")
    for key, spec in registry.items():
        required = {field: spec[field] for field in
                    ("provider", "model", "endpoint", "api_key_env", "accepted_response_models",
                     "model_version_kind", "parameters")}
        if spec["shutdown_date"] is not None:
            required["shutdown_date"] = spec["shutdown_date"]
        for field, value in required.items():
            _same(models[key].get(field), value, "Model configuration mismatch: " + key + "." + field)
        if spec["shutdown_date"] is None and "shutdown_date" in models[key]:
            raise ValueError("Undocumented model shutdown date")
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "effective": effective}
