"""Auditable, bounded execution of registered, reviewed profiling templates.

The registry and SQL code require human/code review: scope labels and the SQL
scanner cannot prove that an arbitrary SELECT is free of patient-level output or
side-effecting functions. This runner accepts no ad hoc SQL or substitutions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import tomllib

from .database import DatabaseError, PsqlClient, validate_timeout, wrap_readonly_query


ALLOWED_SCOPES = frozenset({"metadata", "aggregate", "dictionary"})


@dataclass(frozen=True)
class ProfileQuery:
    name: str
    file: str
    scope: str
    max_rows: int
    completeness: str
    sql: str
    template_sha256: str
    work_mem_mb: int | None


def load_queries(root: Path) -> tuple[list[ProfileQuery], str]:
    """Validate and snapshot all templates before opening a DB connection."""
    registry_bytes = (root / "config" / "profile_queries.toml").read_bytes()
    registry = tomllib.loads(registry_bytes.decode("utf-8"))
    if type(registry.get("schema_version")) is not int or registry["schema_version"] != 1:
        raise ValueError("Profiling registry requires schema_version = 1")
    entries = registry.get("queries")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Profiling registry requires a non-empty [[queries]] list")
    directory = (root / "sql" / "profiling").resolve()
    names, queries = set(), []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("Invalid profiling query entry")
        name = entry.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", name) or name in names:
            raise ValueError("Profiling names must be unique lowercase identifiers")
        names.add(name)
        if not isinstance(entry.get("scope"), str) or entry["scope"] not in ALLOWED_SCOPES:
            raise ValueError("Profiling scope must be metadata, aggregate, or dictionary; patient_rows is prohibited")
        max_rows = entry.get("max_rows")
        if type(max_rows) is not int or not 1 <= max_rows <= 10000:
            raise ValueError("Profiling max_rows must be an integer between 1 and 10000")
        completeness = entry.get("completeness")
        if not isinstance(completeness, str) or not completeness.strip():
            raise ValueError("Every profiling query must describe its completeness limits")
        filename = entry.get("file")
        if not isinstance(filename, str) or not filename.startswith("sql/profiling/"):
            raise ValueError("Profiling files must be inside sql/profiling/")
        path = (root / filename).resolve()
        if not path.is_relative_to(directory) or path.suffix != ".sql" or not path.is_file():
            raise ValueError("Profiling template must resolve to an existing .sql file inside sql/profiling/")
        sql_bytes = path.read_bytes()
        sql = sql_bytes.decode("utf-8")
        work_mem_mb = entry.get("work_mem_mb")
        wrap_readonly_query(sql, max_rows=max_rows, work_mem_mb=work_mem_mb)
        queries.append(ProfileQuery(name, filename, entry["scope"], max_rows, completeness,
                                    sql, hashlib.sha256(sql_bytes).hexdigest(), work_mem_mb))
    return queries, hashlib.sha256(registry_bytes).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_private(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        path.chmod(0o600)
        handle.write(data)


def run_profiles(root: Path, selected: list[str] | None = None, timeout_ms: int = 10000) -> dict:
    """Return only execution metadata; never include database result rows."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    destination = root / "artifacts" / "profiling" / stamp
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    manifest_path = destination / "manifest.json"
    report = {
        "schema_version": 1, "started_at_utc": _utc_now(), "status": "running",
        "read_only": True, "scope": "registered_metadata_aggregate_dictionary",
        "timeout_ms": timeout_ms, "dataset_version_verified": False,
        "queries": [],
        "limitations": "Reviewed static templates only; scope is declared and reviewed, not inferred. Each query runs in its own read-only transaction, not a shared database snapshot. Completeness applies only to each declared query scope; no cohort has been validated.",
    }
    active = None
    try:
        validate_timeout(timeout_ms)
        queries, registry_hash = load_queries(root)
        report["registry_sha256"] = registry_hash
        if selected:
            if len(selected) != len(set(selected)):
                raise ValueError("Repeated --query names are not allowed")
            if set(selected) - {query.name for query in queries}:
                raise ValueError("Unknown --query name; only registered templates may run")
            queries = [query for query in queries if query.name in selected]
        report["selected_queries"] = [query.name for query in queries]
        client = PsqlClient(root, timeout_ms)
        for query in queries:
            wrapped = wrap_readonly_query(query.sql, timeout_ms, max_rows=query.max_rows,
                                          work_mem_mb=query.work_mem_mb)
            active = {
                "query": query.name, "file": query.file, "scope": query.scope,
                "status": "running", "started_at_utc": _utc_now(),
                "max_rows": query.max_rows, "completeness": query.completeness,
                "work_mem_mb": query.work_mem_mb,
                "template_sha256": query.template_sha256,
                "executed_sql_sha256": hashlib.sha256(wrapped.encode("utf-8")).hexdigest(),
                "executed_sql_file": query.name + ".executed.sql",
                "rows": None, "output_sha256": None, "output_persisted": False,
                "completeness_status": "not_evaluated",
            }
            report["queries"].append(active)
            started = time.monotonic()
            try:
                _write_private(destination / active["executed_sql_file"], wrapped.encode("utf-8"))
                csv_text, rows = client._execute_wrapped(wrapped)
                output_bytes = csv_text.encode("utf-8")
                active["rows"] = len(rows)
                active["output_sha256"] = hashlib.sha256(output_bytes).hexdigest()
                if len(rows) > query.max_rows:
                    active["completeness_status"] = "row_limit_exceeded"
                    raise DatabaseError("Profile exceeded its registered output row limit; no CSV was saved. Review query scope before changing its limit.")
                output = destination / (query.name + ".csv")
                _write_private(output, output_bytes)
                active.update(status="complete", output_file=output.name, output_persisted=True,
                              completeness_status="complete_within_declared_scope")
            finally:
                active["finished_at_utc"] = _utc_now()
                active["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["status"] = "complete"
    except (DatabaseError, ValueError, OSError, tomllib.TOMLDecodeError) as exc:
        report["status"] = "failed"
        # Never log raw server errors or arbitrary OS paths (e.g. password files).
        report["error"] = str(exc) if isinstance(exc, (DatabaseError, ValueError)) and not isinstance(exc, tomllib.TOMLDecodeError) else "Profiling configuration or artifact I/O failed."
        if active is not None and active["status"] == "running":
            active["status"] = "failed"
            active["error"] = report["error"]
    finally:
        if report["status"] == "running":
            report["status"] = "failed"
            report["error"] = "Profiling interrupted before completion."
        if active is not None and active["status"] == "running":
            active["status"] = "failed"
        report["finished_at_utc"] = _utc_now()
        _write_private(manifest_path, (json.dumps(report, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    summary = {
        "status": report["status"], "report": str(manifest_path),
        "queries": [{key: query[key] for key in ("query", "scope", "status", "rows", "completeness_status")} for query in report["queries"]],
        "note": "Only execution metadata is printed. Database rows remain in local ignored artifacts; counts are scoped profiling evidence, not cohort validation.",
    }
    if "error" in report:
        summary["error"] = report["error"]
    return summary
