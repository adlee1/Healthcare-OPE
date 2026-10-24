"""Read-only PostgreSQL transport for metadata and registered profiling.

No driver or password is bundled. CLI paths execute reviewed static SQL templates.
This module never creates schemas, tables, extensions, or database roles.
"""
from __future__ import annotations

import csv
import io
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess


QUERY_FILES = (
    "001_database_identity.sql",
    "010_table_inventory.sql",
    "020_column_inventory.sql",
    "030_readiness.sql",
)
CONNECTION_KEYS = frozenset({
    "PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD",
    "PGPASSFILE", "PGSERVICE", "PGSERVICEFILE", "PGSSLMODE", "PGSSLROOTCERT",
    "PGSSLCERT", "PGSSLKEY", "PGCONNECT_TIMEOUT",
})


class DatabaseError(RuntimeError):
    """A deliberately credential-free error safe to show in the terminal."""


def connection_environment(project_root: Path) -> dict[str, str]:
    """Read a small dotenv subset as literal text; process environment wins."""
    env = dict(os.environ)
    dotenv = project_root / ".env"
    if dotenv.is_file():
        for number, line in enumerate(dotenv.read_text().splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                raise DatabaseError(f"Invalid .env assignment on line {number}.")
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if key not in CONNECTION_KEYS:
                raise DatabaseError(f"Unsupported .env key on line {number}; only libpq connection keys are accepted.")
            if value.startswith(("'", '"')):
                if len(value) < 2 or value[-1] != value[0]:
                    raise DatabaseError(f"Unclosed quote in .env on line {number}.")
                value = value[1:-1]
            if value and key not in env:
                env[key] = value
    return env


def connection_status(env: dict[str, str]) -> dict[str, object]:
    return {
        "configured": bool(env.get("PGDATABASE") or env.get("PGSERVICE")),
        "configured_keys": sorted(k for k in CONNECTION_KEYS if env.get(k)),
        "password_values_displayed": False,
    }


def _statement_body(sql: str) -> str:
    """Check reviewed templates, not arbitrary untrusted SQL or function effects.

    Hide quoted values/identifiers and comments before checking statement syntax.
    PostgreSQL standard_conforming_strings is forced on by the execution wrapper.
    Explicit E strings additionally allow backslash escapes. Nested block comments
    and dollar strings are handled to avoid mistaking their contents for commands.
    """
    visible = list(sql)
    length, index = len(sql), 0
    while index < length:
        start = index
        if sql.startswith("--", index):
            end = sql.find("\n", index + 2)
            index = length if end == -1 else end
        elif sql.startswith("/*", index):
            depth, index = 1, index + 2
            while index < length and depth:
                if sql.startswith("/*", index):
                    depth, index = depth + 1, index + 2
                elif sql.startswith("*/", index):
                    depth, index = depth - 1, index + 2
                else:
                    index += 1
            if depth:
                raise ValueError("Unclosed SQL block comment")
        elif sql[index] in ("'", '"'):
            quote = sql[index]
            escaped = quote == "'" and index > 0 and sql[index - 1] in "eE" and (
                index < 2 or not (sql[index - 2].isalnum() or sql[index - 2] in "_$")
            )
            index += 1
            closed = False
            while index < length:
                if escaped and sql[index] == "\\":
                    index += 2
                elif sql[index] == quote:
                    if index + 1 < length and sql[index + 1] == quote:
                        index += 2
                    else:
                        index += 1
                        closed = True
                        break
                else:
                    index += 1
            if not closed:
                raise ValueError("Unclosed SQL quoted value or identifier")
        elif sql[index] == "$":
            match = re.match(r"\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$", sql[index:])
            if not match:
                raise ValueError("Unsupported dollar token in reviewed SQL template")
            delimiter = match.group()
            end = sql.find(delimiter, index + len(delimiter))
            if end == -1:
                raise ValueError("Unclosed SQL dollar string")
            index = end + len(delimiter)
        else:
            index += 1
            continue
        visible[start:index] = " " * (index - start)
    statement = "".join(visible).strip()
    if not re.match(r"^(SELECT|WITH)\b", statement, re.I):
        raise ValueError("Inspection templates must contain exactly one SELECT/WITH statement")
    semicolons = [i for i, character in enumerate(visible) if character == ";"]
    if len(semicolons) > 1 or (semicolons and "".join(visible[semicolons[0] + 1:]).strip()):
        raise ValueError("Inspection templates must contain exactly one SELECT/WITH statement")
    forbidden = (
        "INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|COMMIT|ROLLBACK|"
        "COPY|CALL|DO|SET|RESET|GRANT|REVOKE|INTO|BEGIN|START|ABORT|"
        "SAVEPOINT|RELEASE|PREPARE|EXECUTE|DEALLOCATE|VACUUM|ANALYZE|REINDEX|"
        "REFRESH|DISCARD|LOCK|CHECKPOINT|LOAD|IMPORT"
    )
    if re.search(r"\b(" + forbidden + r")\b", statement, re.I):
        raise ValueError("Inspection templates may not contain transaction or write commands")
    if "\\" in statement or re.search(r"(?<!:):(?!:)", statement):
        raise ValueError("psql meta-commands and variable interpolation are not allowed in inspection templates")
    # Drop only the actual statement terminator, preserving quoted semicolons.
    return (sql[:semicolons[0]] + sql[semicolons[0] + 1:] if semicolons else sql).strip()


def validate_timeout(timeout_ms: int) -> None:
    if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or not 100 <= timeout_ms <= 120000:
        raise ValueError("timeout_ms must be an integer between 100 and 120000")


def wrap_readonly_query(sql: str, timeout_ms: int = 10000, max_rows: int | None = None,
                        work_mem_mb: int | None = None) -> str:
    validate_timeout(timeout_ms)
    if work_mem_mb is not None and (type(work_mem_mb) is not int or not 4 <= work_mem_mb <= 128):
        raise ValueError("work_mem_mb must be an integer between 4 and 128, or omitted")
    statement = _statement_body(sql)
    if max_rows is not None:
        if type(max_rows) is not int or not 1 <= max_rows <= 10000:
            raise ValueError("max_rows must be an integer between 1 and 10000")
        # One additional row distinguishes a complete result from truncation.
        statement = f"SELECT * FROM (\n{statement}\n) AS april_profile_rows LIMIT {max_rows + 1}"
    return (
        "BEGIN READ ONLY;\n"
        f"SET LOCAL statement_timeout = '{timeout_ms}ms';\n"
        "SET LOCAL lock_timeout = '2000ms';\n"
        "SET LOCAL standard_conforming_strings = on;\n"
        + (f"SET LOCAL work_mem = '{work_mem_mb}MB';\n" if work_mem_mb is not None else "")
        + statement + "\n;\nROLLBACK;\n"
    )


def _safe_error(stderr: str) -> str:
    lowered = stderr.lower()
    # psql verbose diagnostics include SQLSTATE; retain only that non-sensitive code.
    match = re.search(r"(?:ERROR|FATAL):\s+([0-9A-Z]{5}):", stderr)
    state = match.group(1) if match else None
    if state and state.startswith(("53", "54")):
        return f"PostgreSQL query exceeded a server resource limit (SQLSTATE {state}). Inspect query planning and local resources before retrying."
    if "password" in lowered or "authentication" in lowered:
        return "PostgreSQL authentication failed. Check the local password file or connection environment."
    if "does not exist" in lowered:
        return "A configured PostgreSQL database, role, or queried schema/relation/column does not exist. Verify the connection and reviewed source schema."
    if "timeout" in lowered or "timed out" in lowered:
        return "PostgreSQL connection or statement exceeded its timeout."
    if "permission denied" in lowered or "operation not permitted" in lowered:
        return "PostgreSQL access was denied by database permissions or the execution environment."
    if "could not translate" in lowered:
        return "PostgreSQL host name could not be resolved. Check PGHOST."
    if "connection" in lowered or "socket" in lowered:
        return "Could not connect to PostgreSQL. Verify host, port, server availability, and network access."
    suffix = f" (SQLSTATE {state})" if state else ""
    return "PostgreSQL inspection failed" + suffix + ". Check the reviewed SQL and database permissions; raw server errors are not logged."


class PsqlClient:
    def __init__(self, project_root: Path, timeout_ms: int = 10000):
        validate_timeout(timeout_ms)
        self.project_root = project_root
        self.timeout_ms = timeout_ms
        self.env = connection_environment(project_root)
        self.psql = shutil.which("psql")
        if not self.psql:
            raise DatabaseError("psql is not on PATH. Install a PostgreSQL client before connecting.")
        if not connection_status(self.env)["configured"]:
            raise DatabaseError("Connection not configured. Set PGDATABASE (and host/port/user) or PGSERVICE in the environment or project .env.")
        # Force bounded defaults even if the calling shell supplies other options.
        self.env["PGCONNECT_TIMEOUT"] = "5"
        self.env["PGAPPNAME"] = "april_reproduction_readonly_inspection"
        self.env["PGOPTIONS"] = f"-c default_transaction_read_only=on -c statement_timeout={timeout_ms} -c lock_timeout=2000 -c standard_conforming_strings=on"

    def query(self, filename: str) -> tuple[str, list[dict[str, str]], str]:
        if filename not in QUERY_FILES:
            raise ValueError("Only registered metadata inspection queries may be executed")
        sql_bytes = (self.project_root / "sql" / filename).read_bytes()
        sql = sql_bytes.decode("utf-8")
        sql_sha256 = hashlib.sha256(sql_bytes).hexdigest()
        wrapped = wrap_readonly_query(sql, self.timeout_ms)
        csv_text, rows = self._execute_wrapped(wrapped)
        if filename == QUERY_FILES[0] and (len(rows) != 1 or rows[0].get("transaction_read_only") != "on"):
            raise DatabaseError("Database identity check did not confirm transaction_read_only=on.")
        return csv_text, rows, sql_sha256

    def _execute_wrapped(self, wrapped: str) -> tuple[str, list[dict[str, str]]]:
        """Internal transport for wrappers constructed from reviewed templates."""
        command = [self.psql, "-X", "--no-password", "--quiet", "--csv", "--set=ON_ERROR_STOP=1", "--set=VERBOSITY=verbose", "--file=-"]
        try:
            result = subprocess.run(command, input=wrapped, text=True, capture_output=True,
                                    env=self.env, timeout=self.timeout_ms / 1000 + 10)
        except subprocess.TimeoutExpired:
            raise DatabaseError("PostgreSQL inspection exceeded the process timeout.") from None
        if result.returncode:
            raise DatabaseError(_safe_error(result.stderr))
        try:
            reader = csv.DictReader(io.StringIO(result.stdout), strict=True)
            fields = reader.fieldnames
            if not fields or len(set(fields)) != len(fields):
                raise DatabaseError("PostgreSQL returned missing or duplicate CSV column names.")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise DatabaseError("PostgreSQL returned malformed CSV rows.")
        except csv.Error:
            raise DatabaseError("PostgreSQL returned malformed CSV data.") from None
        return result.stdout, rows
