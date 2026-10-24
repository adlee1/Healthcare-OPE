"""Real-PostgreSQL, EXPLAIN-only attestation for Query-202 lifecycle A v2.

The attester opens one psql process and one REPEATABLE READ READ ONLY
transaction.  It asks PostgreSQL to plan the nine boundary statements plus
bucket zero of each of the seven physical crosswalk statements.  ``EXPLAIN``
query output is directed
to the operating-system null device by psql, so plans never enter Python,
stdout, stderr, or a persisted file.  Only control markers use stdout.

No artifact is created until an explicit rollback has been observed and psql
has exited with status zero.  The resulting JSON contains template and whole
rendered-statement hashes, timings, and control claims; it contains no SQL,
plan, database value, identifier, relation detail, or column detail.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import struct
import subprocess
import tempfile
import time
from typing import Any, Mapping

from .database import DatabaseError, PsqlClient, _safe_error, _statement_body
from .query202_pre_adjudication import _session_preamble
from .query202_preadjudication_sql_v2 import (
    BOUNDARY_STAGES,
    BUCKET_STATEMENTS,
    COMPONENT_ID,
    render_bucket_sql,
)
from .staged_source_closure import _PersistentPsql


SCHEMA_VERSION = 1
STATEMENT_TIMEOUT_MS = 120_000
CLIENT_WATCHDOG_SECONDS = 135
EXPLAIN_BUCKET_INDEX = 0
MODE = "real_postgresql_read_only_explain_without_analyze"
ATTESTATION_ROOT = Path("artifacts/query202-explain-attestations")
ATTESTATION_FILENAME = "query202-pre-adjudication-v2-explain.json"

SQL_PATHS = tuple(item.sql_path for item in BOUNDARY_STAGES) + tuple(
    item.sql_path for item in BUCKET_STATEMENTS
)

# Every Python file whose runtime behavior is used by this attester is included.
# Tests are deliberately excluded because they are not imported in production.
ATTESTER_BUNDLE_PATHS = (
    "src/april_repro/query202_readonly_explain_attestation.py",
    "scripts/attest_potassium_query202_pre_adjudication_explain.py",
    "src/april_repro/database.py",
    "src/april_repro/staged_source_closure.py",
    "src/april_repro/query202_pre_adjudication.py",
    "src/april_repro/query202_preadjudication_sql_v2.py",
)


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mode(path: Path) -> str:
    return format(stat.S_IMODE(path.stat().st_mode), "04o")


def _safe_relative(relative: str) -> Path:
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or ".." in candidate.parts
        or candidate.as_posix() != relative
    ):
        raise DatabaseError("An EXPLAIN attestation implementation path is unsafe.")
    return candidate


def _bundle(root: Path, paths: tuple[str, ...]) -> dict[str, Any]:
    """Hash a closed file bundle with the Query-202 v2 framing contract."""
    digest = hashlib.sha256()
    files: list[dict[str, Any]] = []
    for relative_text in paths:
        relative = _safe_relative(relative_text)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DatabaseError("A required EXPLAIN attestation file is absent.")
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise DatabaseError("A required EXPLAIN attestation file could not be read.") from exc
        encoded_path = relative_text.encode("utf-8")
        digest.update(struct.pack(">I", len(encoded_path)))
        digest.update(encoded_path)
        digest.update(struct.pack(">Q", len(payload)))
        digest.update(payload)
        files.append({
            "path": relative_text,
            "bytes": len(payload),
            "file_sha256": _sha(payload),
        })
    return {
        "paths": list(paths),
        "bundle_sha256": digest.hexdigest(),
        "files": files,
        "encoding": "uint32be_path_length+path_utf8+uint64be_content_length+content",
    }


def _load_execution_contract(root: Path) -> dict[str, Any]:
    """Load, validate, and hash exactly the sixteen preregistered templates."""
    statements: list[dict[str, Any]] = []
    for ordinal, relative_text in enumerate(SQL_PATHS):
        relative = _safe_relative(relative_text)
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise DatabaseError("A required Query-202 EXPLAIN template is absent.")
        try:
            raw = path.read_bytes()
            template = raw.decode("utf-8")
            bucket_index = None if ordinal < len(BOUNDARY_STAGES) else EXPLAIN_BUCKET_INDEX
            rendered = (
                template
                if bucket_index is None
                else render_bucket_sql(template, bucket_index)
            )
            statement = _statement_body(rendered)
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            raise DatabaseError(
                "A Query-202 EXPLAIN template failed its closed read-only contract."
            ) from exc
        statements.append({
            "ordinal": ordinal,
            "path": relative_text,
            "template_sha256": _sha(raw),
            "rendered_bucket_index": bucket_index,
            "rendered_statement_sha256": _sha(statement.encode("utf-8")),
            "statement": statement,
        })
    if len(statements) != 16:
        raise DatabaseError("The Query-202 EXPLAIN statement inventory is not sixteen.")
    return {
        "statements": statements,
        "sql_bundle": _bundle(root, SQL_PATHS),
    }


def _contract_fingerprint(contract: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        contract["sql_bundle"]["bundle_sha256"],
        tuple(
            (
                item["path"],
                item["template_sha256"],
                item["rendered_bucket_index"],
                item["rendered_statement_sha256"],
            )
            for item in contract["statements"]
        ),
    )


class _DiscardingExplainPsql(_PersistentPsql):
    """Persistent psql whose query output and stderr cannot become files."""

    def __init__(self, client: PsqlClient):
        self._stderr = tempfile.TemporaryFile(mode="w+b")
        os.fchmod(self._stderr.fileno(), 0o600)
        observed = os.fstat(self._stderr.fileno())
        if stat.S_IMODE(observed.st_mode) != 0o600 or observed.st_nlink != 0:
            self._stderr.close()
            raise DatabaseError("The EXPLAIN stderr channel is not anonymous mode 0600.")
        command = [
            client.psql,
            "-X",
            "--no-password",
            "--quiet",
            "--csv",
            "--set=ON_ERROR_STOP=1",
            "--set=VERBOSITY=verbose",
            "--output=" + os.devnull,
            "--file=-",
        ]
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=self._stderr,
                env=client.env,
            )
        except (OSError, ValueError) as exc:
            self._stderr.close()
            raise DatabaseError("The read-only EXPLAIN psql process could not start.") from exc
        self._buffer = bytearray()
        self.safe_stderr_message: str | None = None

    def close(self) -> int:
        """Close psql, reducing anonymous stderr before unlink-on-close."""
        try:
            if self.process.poll() is None and self.process.stdin is not None:
                try:
                    self.process.stdin.write(b"\\q\n")
                    self.process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=2)

            # The process is gone, so seeking this shared file description can
            # no longer alter the child's write offset.  Raw text is reduced to
            # the credential/value-safe database error vocabulary immediately.
            try:
                self._stderr.flush()
                size = self._stderr.seek(0, os.SEEK_END)
                self._stderr.seek(max(0, size - 16_384))
                raw_error = self._stderr.read().decode("utf-8", errors="replace")
                if raw_error.strip():
                    self.safe_stderr_message = _safe_error(raw_error)
            except OSError:
                self.safe_stderr_message = None
        finally:
            self._stderr.close()
        return self.process.returncode if self.process.returncode is not None else -1


def _database_control(marker: str) -> str:
    """Open the transaction and make PostgreSQL prove all three controls.

    ``\\gset`` keeps the three booleans inside psql.  A false boolean exits
    before the success marker, so Python cannot mistake a requested setting for
    an observed database setting.  The control SELECT reads GUC metadata only.
    """
    return (
        _session_preamble()
        + f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        + "SELECT\n"
        + "  current_setting('transaction_read_only') = 'on' "
        + "AS april_explain_read_only_ok,\n"
        + "  current_setting('transaction_isolation') = 'repeatable read' "
        + "AS april_explain_isolation_ok,\n"
        + "  current_setting('statement_timeout') IN "
        + "('120000ms', '120s', '2min') AS april_explain_timeout_ok\n"
        + "\\gset\n"
        + "\\if :april_explain_read_only_ok\n"
        + "\\else\n\\quit 97\n\\endif\n"
        + "\\if :april_explain_isolation_ok\n"
        + "\\else\n\\quit 97\n\\endif\n"
        + "\\if :april_explain_timeout_ok\n"
        + "\\else\n\\quit 97\n\\endif\n"
        + "\\echo "
        + marker
        + "\n"
    )


def _static_explain_control(statement: str) -> str:
    """Return the independently reproducible part of one EXPLAIN control."""
    return (
        f"SET LOCAL statement_timeout = '{STATEMENT_TIMEOUT_MS}ms';\n"
        + "EXPLAIN (FORMAT JSON)\n"
        + statement
        + ";\n"
    )


def _statement_control(statement: str, marker: str) -> str:
    return (
        _static_explain_control(statement)
        + "\\echo "
        + marker
        + "\n"
    )


def _update_transcript(digest: Any, control: str) -> None:
    encoded = control.encode("utf-8")
    digest.update(struct.pack(">Q", len(encoded)))
    digest.update(encoded)


def _git_ignored(root: Path, path: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    try:
        result = subprocess.run(
            [
                "git",
                "check-ignore",
                "--quiet",
                "--no-index",
                "--",
                relative.as_posix(),
            ],
            cwd=root,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _atomic_write_private(path: Path, payload: bytes) -> None:
    temporary = path.with_name("." + path.name + "." + secrets.token_hex(16) + ".tmp")
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(temporary, flags, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _persist_attestation(root: Path, relative: Path, payload: bytes) -> Path:
    destination = root / relative
    category = destination.parent.parent
    run_directory = destination.parent
    created_category = False
    created_run = False
    try:
        if category.exists():
            if not category.is_dir() or category.is_symlink():
                raise DatabaseError("The EXPLAIN attestation artifact root is unsafe.")
            category.chmod(0o700)
        else:
            category.mkdir(parents=True, mode=0o700)
            category.chmod(0o700)
            created_category = True
        run_directory.mkdir(mode=0o700)
        run_directory.chmod(0o700)
        created_run = True
        if not _git_ignored(root, destination):
            raise DatabaseError("The EXPLAIN attestation destination is not git-ignored.")
        _atomic_write_private(destination, payload)
        if _mode(run_directory) != "0700" or _mode(destination) != "0600":
            raise DatabaseError("The EXPLAIN attestation artifact modes are unsafe.")
        return destination
    except BaseException:
        try:
            destination.unlink(missing_ok=True)
        except OSError:
            pass
        if created_run:
            try:
                run_directory.rmdir()
            except OSError:
                pass
        if created_category:
            try:
                category.rmdir()
            except OSError:
                pass
        raise


def _terminal_result(root: Path, path: Path, payload: bytes, attestation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "passed",
        "component_id": COMPONENT_ID,
        "mode": MODE,
        "attestation": path.relative_to(root).as_posix(),
        "attestation_sha256": _sha(payload),
        "statement_count": attestation["statement_count"],
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "client_watchdog_seconds": CLIENT_WATCHDOG_SECONDS,
        "rollback_confirmed": True,
        "psql_returncode": 0,
        "plan_output_discarded": True,
        "raw_values_persisted": False,
    }


def run_query202_readonly_explain_attestation(root: Path) -> dict[str, Any]:
    """Execute the sixteen EXPLAIN-only checks and persist a success attestation."""
    root = root.resolve()
    contract = _load_execution_contract(root)
    attester_bundle = _bundle(root, ATTESTER_BUNDLE_PATHS)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    relative = ATTESTATION_ROOT / stamp / ATTESTATION_FILENAME
    destination = root / relative
    if destination.exists() or destination.is_symlink():
        raise DatabaseError("The EXPLAIN attestation destination already exists.")
    if not _git_ignored(root, destination):
        raise DatabaseError("The EXPLAIN attestation destination is not git-ignored.")

    started_at = _now()
    started = time.monotonic()
    session: _DiscardingExplainPsql | None = None
    transaction_started = False
    rollback_confirmed = False
    psql_returncode: int | None = None
    safe_server_error: str | None = None
    failure: str | None = None
    elapsed_by_statement: list[float] = []
    database_control_elapsed = 0.0
    transcript = hashlib.sha256()
    stdout_frames_empty = True

    try:
        client = PsqlClient(root, STATEMENT_TIMEOUT_MS)
        session = _DiscardingExplainPsql(client)
        database_marker = (
            "__APRIL_QUERY202A_V2_EXPLAIN_DATABASE_CONTROL_"
            + secrets.token_hex(24)
            + "__"
        )
        database_control = _database_control(database_marker)
        _update_transcript(transcript, database_control)
        began = time.monotonic()
        try:
            transaction_started = True
            session.send(database_control)
            database_frame = session.frame(
                database_marker, CLIENT_WATCHDOG_SECONDS, 0
            )
        finally:
            database_control_elapsed = round(time.monotonic() - began, 6)
        if database_frame != b"":
            stdout_frames_empty = False
            raise DatabaseError(
                "The EXPLAIN database-control channel contained query output."
            )

        for item in contract["statements"]:
            marker = "__APRIL_QUERY202A_V2_EXPLAIN_" + secrets.token_hex(24) + "__"
            control = _statement_control(item["statement"], marker)
            _update_transcript(transcript, control)
            began = time.monotonic()
            try:
                session.send(control)
                # Query output goes to os.devnull.  Therefore even one byte
                # before the random control marker is an invariant failure.
                frame = session.frame(marker, CLIENT_WATCHDOG_SECONDS, 0)
            finally:
                elapsed_by_statement.append(round(time.monotonic() - began, 6))
            if frame != b"":
                stdout_frames_empty = False
                raise DatabaseError("The EXPLAIN psql control channel contained query output.")

        rollback_marker = "__APRIL_QUERY202A_V2_EXPLAIN_ROLLBACK_" + secrets.token_hex(24) + "__"
        rollback_control = "ROLLBACK;\n\\echo " + rollback_marker + "\n"
        _update_transcript(transcript, rollback_control)
        session.confirm_rollback(rollback_marker)
        rollback_confirmed = True
        _update_transcript(transcript, "\\q\n")
        closing = session
        try:
            psql_returncode = closing.close()
        finally:
            safe_server_error = getattr(closing, "safe_stderr_message", None)
            session = None
        if psql_returncode != 0:
            raise DatabaseError("The EXPLAIN psql process did not exit cleanly after rollback.")
    except DatabaseError as exc:
        failure = str(exc)
    except Exception:
        failure = "The read-only EXPLAIN attestation failed before safe persistence."
    finally:
        if session is not None:
            if transaction_started and not rollback_confirmed:
                try:
                    marker = "__APRIL_QUERY202A_V2_EXPLAIN_ABORT_" + secrets.token_hex(24) + "__"
                    session.confirm_rollback(marker)
                except BaseException:
                    pass
            closing = session
            try:
                psql_returncode = closing.close()
            except BaseException:
                psql_returncode = None
            safe_server_error = getattr(closing, "safe_stderr_message", None)
            session = None

    if failure is not None:
        raise DatabaseError(safe_server_error or failure)
    if not rollback_confirmed or psql_returncode != 0:
        raise DatabaseError("EXPLAIN evidence cannot persist before rollback and clean exit.")

    # Fail closed if any SQL or attester implementation file moved while the
    # connection was open.  The attestation then describes exactly current,
    # reviewable source bytes.
    after_contract = _load_execution_contract(root)
    after_attester_bundle = _bundle(root, ATTESTER_BUNDLE_PATHS)
    if _contract_fingerprint(after_contract) != _contract_fingerprint(contract):
        raise DatabaseError("The Query-202 EXPLAIN SQL changed during execution.")
    if after_attester_bundle != attester_bundle:
        raise DatabaseError("The Query-202 EXPLAIN attester changed during execution.")

    finished_at = _now()
    statement_metadata = [
        {
            "path": item["path"],
            "template_sha256": item["template_sha256"],
            "rendered_bucket_index": item["rendered_bucket_index"],
            "explain_only": True,
            "analyze": False,
            "status": "passed",
            "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        }
        for item in contract["statements"]
    ]
    rendered_hashes = [
        {
            "ordinal": item["ordinal"],
            "path": item["path"],
            "rendered_bucket_index": item["rendered_bucket_index"],
            "rendered_statement_sha256": item["rendered_statement_sha256"],
            "explain_control_sha256": _sha(
                _static_explain_control(item["statement"]).encode("utf-8")
            ),
        }
        for item in contract["statements"]
    ]
    attestation: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "component_id": COMPONENT_ID,
        "status": "passed",
        "mode": MODE,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "database_connection_opened": True,
        "synthetic_postgresql_fixture": False,
        "single_transaction": True,
        "transaction_read_only": True,
        "transaction_isolation": "repeatable read",
        "database_controls_observed_before_explain": True,
        "database_control_checks": {
            "transaction_read_only_on": True,
            "transaction_isolation_repeatable_read": True,
            "statement_timeout_120000ms": True,
        },
        "database_control_elapsed_seconds": database_control_elapsed,
        "statement_timeout_ms": STATEMENT_TIMEOUT_MS,
        "client_watchdog_seconds": CLIENT_WATCHDOG_SECONDS,
        "statement_count": len(statement_metadata),
        "analyze_used": False,
        "explain_syntax": "EXPLAIN (FORMAT JSON)",
        "database_writes_or_session_objects": False,
        "on_error_stop": True,
        "rollback_confirmed": True,
        "psql_returncode": 0,
        "query_output_redirected_to_os_null": True,
        "stdout_control_frames_empty": stdout_frames_empty,
        "plan_output_discarded": True,
        "plan_output_persisted": False,
        "stderr_anonymous_unlinked": True,
        "stderr_persisted": False,
        "sql_text_persisted": False,
        "raw_values_persisted": False,
        "patient_or_event_identifiers_persisted": False,
        "query_plan_relation_or_column_details_persisted": False,
        "success_persisted_only_after_rollback_and_clean_exit": True,
        "sql_bundle_sha256": contract["sql_bundle"]["bundle_sha256"],
        "attester_bundle_sha256": attester_bundle["bundle_sha256"],
        "attester_paths": attester_bundle["paths"],
        "attester_files": attester_bundle["files"],
        "bundle_hash_encoding": attester_bundle["encoding"],
        "control_transcript_sha256": transcript.hexdigest(),
        "control_transcript_hash_framing": "uint64be_control_utf8_length+control_utf8",
        "statement_elapsed_seconds": elapsed_by_statement,
        "statements": statement_metadata,
        "rendered_statements": rendered_hashes,
        "artifact_directory_mode": "0700",
        "artifact_file_mode": "0600",
        "artifact_git_ignored": True,
    }
    payload = (
        json.dumps(attestation, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    path = _persist_attestation(root, relative, payload)
    return _terminal_result(root, path, payload, attestation)

