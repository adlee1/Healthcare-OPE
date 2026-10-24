"""Verify saved aggregate-query evidence against the current reviewed templates.

This proves local content consistency, not source authenticity, a shared
database snapshot, or scientific cohort validity. No database connection.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from .database import wrap_readonly_query
from .profiling import load_queries


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _local_file(directory: Path, filename: str) -> Path:
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise ValueError("Evidence filenames must be local basenames")
    path = directory / filename
    if not path.is_file() or path.resolve().parent != directory.resolve():
        raise ValueError("Evidence file is missing or escapes its run directory")
    return path


def verify_profile_evidence(root: Path) -> dict:
    queries, registry_hash = load_queries(root)
    manifests = []
    invalid_manifest_files = 0
    for path in sorted((root / "artifacts" / "profiling").glob("*/manifest.json"), reverse=True):
        try:
            report = json.loads(path.read_text())
            if not isinstance(report, dict) or not isinstance(report.get("queries"), list):
                raise ValueError("Invalid evidence manifest")
            manifests.append((path, report))
        except (OSError, ValueError):
            invalid_manifest_files += 1
    findings = []
    for query in queries:
        found = None
        rejected = 0
        for path, report in manifests:
            for entry in report["queries"]:
                if not isinstance(entry, dict) or entry.get("query") != query.name:
                    continue
                if entry.get("status") != "complete" or entry.get("template_sha256") != query.template_sha256:
                    continue
                try:
                    expected = wrap_readonly_query(query.sql, report["timeout_ms"],
                        max_rows=query.max_rows, work_mem_mb=query.work_mem_mb).encode()
                    actual = _local_file(path.parent, entry["executed_sql_file"]).read_bytes()
                    output = _local_file(path.parent, entry["output_file"]).read_bytes()
                    reader = csv.DictReader(io.StringIO(output.decode()), strict=True)
                    rows = list(reader)
                    if (not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames))
                            or any(None in row or any(value is None for value in row.values()) for row in rows)):
                        raise ValueError("Malformed aggregate CSV")
                    checks = (
                        report.get("read_only") is True,
                        entry.get("scope") == query.scope,
                        entry.get("completeness") == query.completeness,
                        entry.get("file") == query.file,
                        entry.get("max_rows") == query.max_rows,
                        entry.get("work_mem_mb") == query.work_mem_mb,
                        entry.get("output_persisted") is True,
                        entry.get("completeness_status") == "complete_within_declared_scope",
                        actual == expected,
                        _digest(actual) == entry.get("executed_sql_sha256"),
                        _digest(output) == entry.get("output_sha256"),
                        len(rows) == entry.get("rows"),
                        len(rows) <= query.max_rows,
                    )
                    if not all(checks):
                        raise ValueError("Evidence metadata or hash mismatch")
                    found = {
                        "query": query.name, "status": "verified",
                        "manifest": str(path.relative_to(root)),
                        "template_sha256": query.template_sha256,
                        "executed_sql_sha256": _digest(actual),
                        "output_sha256": _digest(output), "rows": len(rows),
                        "execution_registry_sha256": report.get("registry_sha256"),
                    }
                    break
                except (KeyError, OSError, ValueError, TypeError, csv.Error):
                    rejected += 1
            if found:
                break
        findings.append((found or {"query": query.name, "status": "missing_current_evidence"})
                        | {"rejected_matching_entries": rejected})
    return {
        "status": "verified" if all(row["status"] == "verified" for row in findings) else "incomplete",
        "current_registry_sha256": registry_hash,
        "query_count": len(queries), "invalid_manifest_files": invalid_manifest_files,
        "queries": findings,
        "limitations": "Individual local template, execution, output and row-count consistency only. Historical successful entries can come from a failed batch because queries use separate transactions. Different registry versions/runs are not one database snapshot; this does not validate source authenticity or a cohort.",
    }
