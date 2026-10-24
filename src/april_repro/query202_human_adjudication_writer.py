"""Apply human-authored Query-202 adjudication transactions safely.

The request is a private, exact-schema JSON document.  It contains the human
reviewer's controlled clinical decisions, rationale, and times.  This module
only supplies mechanical sequence numbers, predecessor hashes, event-chain
records, attestation bindings, and the optional terminal transition.

Updates are made to a complete private sibling copy.  The copy must pass the
normal workspace validator before it can replace the live workspace through a
single atomic directory exchange.  Reports and exceptions never reproduce
review IDs, source values, rationale, evidence paths, or document names.
"""
from __future__ import annotations

import ctypes
from datetime import datetime
import errno
import fcntl
import hashlib
import os
from pathlib import Path
import secrets
import stat
import struct
import sys
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import query202_human_adjudication as workspace_api


CONFIG_PATH = workspace_api.CONFIG_PATH
COMPONENT_ID = workspace_api.COMPONENT_ID
TRANSACTION_TYPE = "human_adjudication_update"
TRANSACTION_SCHEMA_VERSION = 1
WORKSPACE_SNAPSHOT_HASH_VERSION = "query202-human-workspace-file-snapshot-v1"
MAX_TRANSACTION_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_DOCUMENT_BYTES = 128 * 1024 * 1024
MAX_IMPORTED_DOCUMENT_BYTES_PER_TRANSACTION = 256 * 1024 * 1024
MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES = 2 * 1024 * 1024 * 1024
LOCK_SUFFIX = ".human-adjudication.lock"
STAGE_PREFIX = ".txn-human-adjudication-"

TOP_LEVEL_FIELDS = frozenset({
    "schema_version",
    "component_id",
    "transaction_type",
    "workspace",
    "expected_workspace_snapshot_sha256",
    "reviewer_id",
    "submitted_at_utc",
    "operations",
})
OPERATION_FIELDS = frozenset({
    "evidence_additions",
    "semantic_revisions",
    "route_revisions",
    "mapping_group_revisions",
    "attestations",
    "terminal_event",
})
SEMANTIC_OPERATION_FIELDS = frozenset({
    "review_id",
    "revision_reason",
    "review_status",
    "dimensions",
    "mapping_group_id",
    "rationale",
    "reviewed_at_utc",
})
ROUTE_OPERATION_FIELDS = frozenset({
    "review_id",
    "revision_reason",
    "review_status",
    "decision",
    "decision_basis",
    "evidence_refs",
    "rationale",
    "reviewed_at_utc",
})
GROUP_OPERATION_FIELDS = frozenset({
    "mapping_group_id",
    "revision_reason",
    "review_status",
    "member_review_ids",
    "local_evidence_refs",
    "dimensions",
    "rationale",
    "reviewed_at_utc",
})
ATTESTATION_OPERATION_FIELDS = frozenset({
    "review_kind",
    "batch_index",
    "attested_at_utc",
    "attestation_method",
    "confirm_complete",
    "confirm_review_policy_version",
})
LOCAL_OR_TEMPLATE_EVIDENCE_FIELDS = frozenset({
    "evidence_id", "namespace", "locator"
})
DOCUMENT_EVIDENCE_FIELDS = frozenset({
    "evidence_id",
    "namespace",
    "source_private_path",
    "expected_document_sha256",
    "document_version",
    "accessed_at_utc",
})
COMPLETION_FIELDS = frozenset({
    "event_type", "event_at_utc", "confirm_all_batches_complete"
})
ABANDON_FIELDS = frozenset({"event_type", "event_at_utc", "reason"})

_TEST_FAILURE_INJECTOR: Callable[[str], None] | None = None


class HumanAdjudicationWriterError(workspace_api.HumanAdjudicationError):
    """A private authoring request or atomic workspace update failed closed."""


def _fail(message: str) -> None:
    raise HumanAdjudicationWriterError(message)


def _inject(point: str) -> None:
    hook = _TEST_FAILURE_INJECTOR
    if hook is not None:
        hook(point)


def _exact(value: object, fields: Iterable[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(fields):
        _fail(f"{label} does not have the exact required schema.")
    return value


def _strict_utc(value: object, label: str) -> str:
    if not workspace_api._strict_utc(value):
        _fail(f"{label} is not a strict UTC time.")
    assert isinstance(value, str)
    return value


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value[:-1] + "+00:00")


def _bounded_text(value: object, label: str, maximum: int = workspace_api.MAX_TEXT_BYTES) -> str:
    try:
        return workspace_api._nonempty_text(value, label, maximum)
    except workspace_api.HumanAdjudicationError as error:
        raise HumanAdjudicationWriterError(str(error)) from None


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _sequence_hash(version: str, records: Sequence[Mapping[str, Any]]) -> str:
    domain = version.encode("utf-8")
    digest = hashlib.sha256()
    digest.update(struct.pack(">I", len(domain)))
    digest.update(domain)
    digest.update(struct.pack(">Q", len(records)))
    for record in records:
        encoded = workspace_api._canonical_json(record)
        digest.update(struct.pack(">Q", len(encoded)))
        digest.update(encoded)
    return digest.hexdigest()


def _snapshot_bounded_file(
    path: Path,
    label: str,
    maximum_bytes: int,
    *,
    retain_payload: bool = False,
    require_nonempty: bool = False,
) -> dict[str, Any]:
    """Snapshot one regular file without reading beyond its accepted bound.

    The ordinary workspace snapshot helper deliberately has no size policy.
    Private transaction and evidence inputs do: check the named and opened
    inode sizes before I/O, stop after at most ``maximum_bytes + 1`` observed
    bytes if a concurrent writer grows the file, and then apply the same
    pathname/inode closure used by the workspace reader.
    """
    if type(maximum_bytes) is not int or maximum_bytes < 0:
        _fail("An internal private-file byte limit is invalid.")
    parent_fd: int | None = None
    descriptor: int | None = None
    payload: list[bytes] | None = [] if retain_payload else None
    digest = hashlib.sha256()
    total = 0
    try:
        parent_fd, name, parent_chain = workspace_api._open_parent_fd(path)
        initial = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(initial.st_mode):
            _fail(f"{label} must be one regular file.")
        if initial.st_size > maximum_bytes or (
            require_nonempty and initial.st_size == 0
        ):
            _fail(f"{label} is outside its byte bound.")
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not workspace_api._same_open_snapshot(initial, before)
            or before.st_size > maximum_bytes
            or (require_nonempty and before.st_size == 0)
        ):
            _fail(f"{label} changed before it was read or is outside its byte bound.")
        while True:
            # The extra byte detects growth past the limit without allowing an
            # unbounded read even when the inode size changes after fstat.
            read_size = min(
                workspace_api.READ_CHUNK_BYTES,
                maximum_bytes - total + 1,
            )
            chunk = os.read(descriptor, read_size)
            if not chunk:
                break
            total += len(chunk)
            if total > maximum_bytes:
                _fail(f"{label} grew beyond its byte bound while it was read.")
            digest.update(chunk)
            if payload is not None:
                payload.append(chunk)
        after = os.fstat(descriptor)
        final_at_parent = os.stat(
            name, dir_fd=parent_fd, follow_symlinks=False
        )
    except HumanAdjudicationWriterError:
        raise
    except (workspace_api.HumanAdjudicationError, OSError):
        _fail(f"{label} could not be read safely within its byte bound.")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if parent_fd is not None:
            os.close(parent_fd)
    try:
        final, final_parent_chain = workspace_api._lstat_nofollow(path)
    except workspace_api.HumanAdjudicationError:
        _fail(f"{label} changed while it was read.")
    if (
        not workspace_api._same_open_snapshot(before, after)
        or not workspace_api._same_open_snapshot(after, final_at_parent)
        or not workspace_api._same_open_snapshot(final_at_parent, final)
        or parent_chain != final_parent_chain
        or total != after.st_size
        or total > maximum_bytes
        or (require_nonempty and total == 0)
    ):
        _fail(f"{label} changed while it was read or is outside its byte bound.")
    return {
        "sha256": digest.hexdigest(),
        "bytes": total,
        "mode": stat.S_IMODE(after.st_mode),
        "nlink": after.st_nlink,
        "identity": (after.st_dev, after.st_ino),
        "parent_chain": parent_chain,
        "payload": b"".join(payload) if payload is not None else None,
    }


def _workspace_snapshot_pass(
    workspace: Path,
) -> tuple[
    dict[str, Mapping[str, Any]],
    dict[str, Mapping[str, Any]],
]:
    files, directories = workspace_api._walk_workspace_files(workspace)
    directory_snapshots: dict[str, Mapping[str, Any]] = {}
    for path in directories:
        relative = path.relative_to(workspace).as_posix()
        directory_snapshots[relative] = workspace_api._snapshot_directory(
            path, "A human-adjudication workspace directory"
        )
    file_snapshots: dict[str, Mapping[str, Any]] = {}
    for relative in sorted(files):
        snapshot = workspace_api._snapshot_file(
            workspace / relative, "A human-adjudication workspace file"
        )
        metadata, parent_chain = workspace_api._lstat_nofollow(workspace / relative)
        if (
            metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != snapshot["identity"]
            or parent_chain != snapshot["parent_chain"]
        ):
            _fail("A private workspace file changed or has more than one hard link.")
        file_snapshots[relative] = snapshot
    return file_snapshots, directory_snapshots


def _workspace_snapshot_hash(workspace: Path) -> tuple[str, tuple[int, int], tuple[tuple[int, int], ...]]:
    first_files, first_directories = _workspace_snapshot_pass(workspace)
    second_files, second_directories = _workspace_snapshot_pass(workspace)
    if (
        set(first_files) != set(second_files)
        or set(first_directories) != set(second_directories)
        or any(
            workspace_api._seal(first_files[relative])
            != workspace_api._seal(second_files[relative])
            for relative in first_files
        )
        or any(
            workspace_api._directory_seal(first_directories[relative])
            != workspace_api._directory_seal(second_directories[relative])
            for relative in first_directories
        )
    ):
        _fail("The workspace changed while its optimistic-concurrency hash was computed.")
    inventory: list[dict[str, Any]] = []
    for relative in sorted(second_files):
        snapshot = second_files[relative]
        inventory.append({
            "file": relative,
            "sha256": snapshot["sha256"],
            "bytes": snapshot["bytes"],
            "mode": f"{snapshot['mode']:04o}",
        })
    root_snapshot = second_directories.get(".")
    if root_snapshot is None:
        _fail("The workspace snapshot lacks its root directory.")
    return (
        _sequence_hash(WORKSPACE_SNAPSHOT_HASH_VERSION, inventory),
        root_snapshot["identity"],
        root_snapshot["parent_chain"],
    )


def inspect_human_adjudication_workspace(
    root: Path,
    workspace_directory: Path,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Return an aggregate-only authoring base report for a formal workspace."""
    root = root.resolve(strict=True)
    report = workspace_api.validate_human_adjudication_workspace(
        root, workspace_directory, config_path=config_path
    )
    if (
        not report.get("valid")
        or report.get("formal_workspace") is not True
        or report.get("status") not in {"initialized", "review_in_progress"}
        or report.get("reviewed_semantic_ledger_frozen") is not False
        or report.get("route_mapping_frozen") is not False
    ):
        _fail("The workspace lifecycle does not permit an authoring transaction.")
    relative = workspace_api._safe_relative(
        workspace_directory.as_posix(), "human-adjudication workspace"
    )
    path = workspace_api._project_path(
        root, relative.as_posix(), "human-adjudication workspace"
    )
    digest, _, _ = _workspace_snapshot_hash(path)
    return {
        "status": report["status"],
        "formal_workspace": True,
        "workspace": relative.as_posix(),
        "workspace_snapshot_hash_version": WORKSPACE_SNAPSHOT_HASH_VERSION,
        "workspace_snapshot_sha256": digest,
        "semantic_items": report["semantic_items"],
        "reviewed_semantic_items": report["reviewed_semantic_items"],
        "route_items": report["route_items"],
        "reviewed_route_items": report["reviewed_route_items"],
        "mapping_groups": report["mapping_groups"],
        "database_connected": False,
        "external_api_called": False,
        "llm_called": False,
    }


def _load_private_transaction(root: Path, relative: Path) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    safe = workspace_api._safe_relative(relative.as_posix(), "authoring transaction")
    path = workspace_api._project_path(root, safe.as_posix(), "authoring transaction")
    snapshot = _snapshot_bounded_file(
        path,
        "The private authoring transaction",
        MAX_TRANSACTION_BYTES,
        retain_payload=True,
    )
    metadata, _ = workspace_api._lstat_nofollow(path)
    if (
        snapshot["mode"] != 0o600
        or metadata.st_nlink != 1
        or not workspace_api._git_ignored(root, path)
    ):
        _fail("The authoring transaction is not a bounded private Git-ignored file.")
    try:
        parsed = workspace_api._json_loads(
            snapshot["payload"], "The private authoring transaction"
        )
    except workspace_api.HumanAdjudicationError as error:
        raise HumanAdjudicationWriterError(str(error)) from None
    transaction = _exact(parsed, TOP_LEVEL_FIELDS, "The authoring transaction")
    return transaction, {**snapshot, "path": path, "relative": safe}


def _validate_transaction_envelope(transaction: Mapping[str, Any]) -> tuple[Path, str, str, Mapping[str, Any]]:
    if (
        transaction["schema_version"] != TRANSACTION_SCHEMA_VERSION
        or transaction["component_id"] != COMPONENT_ID
        or transaction["transaction_type"] != TRANSACTION_TYPE
    ):
        _fail("The authoring transaction identity or schema version is invalid.")
    workspace = workspace_api._safe_relative(
        transaction["workspace"], "transaction workspace"
    )
    expected = transaction["expected_workspace_snapshot_sha256"]
    if not isinstance(expected, str) or workspace_api.SHA256_RE.fullmatch(expected) is None:
        _fail("The expected workspace snapshot hash is invalid.")
    reviewer = _bounded_text(transaction["reviewer_id"], "reviewer ID", 256)
    submitted = _strict_utc(transaction["submitted_at_utc"], "transaction submission time")
    operations = _exact(transaction["operations"], OPERATION_FIELDS, "Transaction operations")
    for key in OPERATION_FIELDS - {"terminal_event"}:
        if not isinstance(operations[key], list):
            _fail("Every transaction operation collection must be a list.")
    if operations["terminal_event"] is not None and not isinstance(
        operations["terminal_event"], Mapping
    ):
        _fail("The terminal operation is invalid.")
    if not any(operations[key] for key in OPERATION_FIELDS):
        _fail("An empty authoring transaction is not permitted.")
    return workspace, expected, reviewer, {**operations, "_submitted_at_utc": submitted}


def _acquire_lock(root: Path, workspace: Path) -> tuple[int, int, str, tuple[tuple[int, int], ...]]:
    parent_path = root / workspace.parent
    parent_fd, parent_chain = workspace_api._open_directory_fd(parent_path)
    lock_name = f".{workspace.name}{LOCK_SUFFIX}"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        lock_fd = os.open(lock_name, flags, 0o600, dir_fd=parent_fd)
        lock_stat = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or stat.S_IMODE(lock_stat.st_mode) != 0o600
            or lock_stat.st_nlink != 1
        ):
            _fail("The external authoring lock is not a private regular file.")
        os.fchmod(lock_fd, 0o600)
        if not workspace_api._git_ignored(root, parent_path / lock_name):
            _fail("The external authoring lock is not Git-ignored.")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _fail("Another authoring transaction holds the workspace lock.")
        os.fsync(lock_fd)
        return parent_fd, lock_fd, lock_name, parent_chain
    except BaseException:
        if "lock_fd" in locals():
            os.close(lock_fd)
        os.close(parent_fd)
        raise


def _assert_lock_closure(parent_fd: int, lock_fd: int, lock_name: str) -> None:
    try:
        opened = os.fstat(lock_fd)
        named = os.stat(lock_name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        _fail("The external authoring lock changed while the transaction ran.")
    if (
        not stat.S_ISREG(opened.st_mode)
        or not stat.S_ISREG(named.st_mode)
        or stat.S_IMODE(opened.st_mode) != 0o600
        or stat.S_IMODE(named.st_mode) != 0o600
        or opened.st_nlink != 1
        or named.st_nlink != 1
        or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
    ):
        _fail("The external authoring lock changed while the transaction ran.")


def _relative_parent_fd(base_fd: int, relative: Path) -> tuple[int, str]:
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("An internal workspace path is unsafe.")
    descriptor = os.dup(base_fd)
    try:
        for part in relative.parts[:-1]:
            next_descriptor = os.open(
                part, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=descriptor
            )
            before = os.fstat(next_descriptor)
            if not stat.S_ISDIR(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o700:
                os.close(next_descriptor)
                _fail("An internal workspace directory is unsafe.")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor, relative.parts[-1]
    except BaseException:
        os.close(descriptor)
        raise


def _copy_regular_file(source_fd: int, source_name: str, destination_fd: int, destination_name: str) -> None:
    read_flags = os.O_RDONLY
    write_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        read_flags |= os.O_NOFOLLOW
        write_flags |= os.O_NOFOLLOW
    source = os.open(source_name, read_flags, dir_fd=source_fd)
    destination: int | None = None
    try:
        before = os.fstat(source)
        if (
            not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
        ):
            _fail("A workspace file is not a private regular file.")
        destination = os.open(destination_name, write_flags, 0o600, dir_fd=destination_fd)
        os.fchmod(destination, 0o600)
        while True:
            chunk = os.read(source, workspace_api.READ_CHUNK_BYTES)
            if not chunk:
                break
            view = memoryview(chunk)
            while view:
                written = os.write(destination, view)
                if written <= 0:
                    _fail("A staged workspace file could not be copied completely.")
                view = view[written:]
        after = os.fstat(source)
        if not workspace_api._same_open_snapshot(before, after):
            _fail("The workspace changed while its staged copy was made.")
        os.fsync(destination)
    finally:
        if destination is not None:
            os.close(destination)
        os.close(source)


def _copy_tree_fd(source_fd: int, destination_fd: int) -> None:
    for name in sorted(os.listdir(source_fd)):
        source_stat = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        mode = stat.S_IMODE(source_stat.st_mode)
        if stat.S_ISREG(source_stat.st_mode):
            if mode != 0o600:
                _fail("A workspace file has an unsafe mode during staging.")
            _copy_regular_file(source_fd, name, destination_fd, name)
        elif stat.S_ISDIR(source_stat.st_mode):
            if mode != 0o700:
                _fail("A workspace directory has an unsafe mode during staging.")
            os.mkdir(name, 0o700, dir_fd=destination_fd)
            source_child = os.open(
                name, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=source_fd
            )
            destination_child = os.open(
                name, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=destination_fd
            )
            try:
                _copy_tree_fd(source_child, destination_child)
                os.fsync(destination_child)
            finally:
                os.close(destination_child)
                os.close(source_child)
        else:
            _fail("A workspace entry is neither a regular file nor a directory.")


def _stage_workspace(parent_fd: int, workspace_name: str) -> tuple[str, int, tuple[int, int]]:
    stale_prefix = f"{STAGE_PREFIX}{workspace_name}-"
    if any(name.startswith(stale_prefix) for name in os.listdir(parent_fd)):
        _fail("A stale authoring stage requires manual recovery before another update.")
    source_fd = os.open(
        workspace_name, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd
    )
    try:
        source_stat = os.fstat(source_fd)
        if stat.S_IMODE(source_stat.st_mode) != 0o700:
            _fail("The live workspace directory mode is unsafe.")
        for _ in range(100):
            stage_name = stale_prefix + secrets.token_hex(12)
            try:
                os.mkdir(stage_name, 0o700, dir_fd=parent_fd)
                break
            except FileExistsError:
                continue
        else:
            _fail("A unique private authoring stage could not be allocated.")
        stage_fd = os.open(
            stage_name, workspace_api.DIRECTORY_OPEN_FLAGS, dir_fd=parent_fd
        )
        try:
            os.fchmod(stage_fd, 0o700)
            _copy_tree_fd(source_fd, stage_fd)
            os.fsync(stage_fd)
            identity = (os.fstat(stage_fd).st_dev, os.fstat(stage_fd).st_ino)
            return stage_name, stage_fd, identity
        except BaseException:
            os.close(stage_fd)
            workspace_api._remove_tree_at(parent_fd, stage_name)
            raise
    finally:
        os.close(source_fd)


def _read_records(path: Path, label: str) -> list[Mapping[str, Any]]:
    snapshot = workspace_api._snapshot_file(path, label, retain_payload=True)
    if snapshot["mode"] != 0o600:
        _fail("A staged workspace ledger has an unsafe mode.")
    return workspace_api._read_ndjson_snapshot(snapshot, label)


def _append_records(stage_fd: int, relative: str, records: Sequence[Mapping[str, Any]]) -> None:
    if not records:
        return
    parent_fd, name = _relative_parent_fd(stage_fd, Path(relative))
    flags = os.O_WRONLY | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor: int | None = None
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode) != 0o600:
            _fail("A staged workspace ledger is unsafe.")
        payload = b"".join(workspace_api._json_line(record) for record in records)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("A staged workspace ledger could not be updated completely.")
            view = view[written:]
        os.fsync(descriptor)
        os.fsync(parent_fd)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)


def _versioned_document_total(workspace: Path) -> int:
    """Return a closure-checked total for all imported workspace documents."""
    documents = workspace / "evidence-registry/documents"
    initial_directory = workspace_api._snapshot_directory(
        documents, "The workspace versioned-document directory"
    )
    if initial_directory["mode"] != 0o700:
        _fail("The workspace versioned-document directory has an unsafe mode.")
    total = 0
    for name in initial_directory["entries"]:
        if not isinstance(name, str) or not name or Path(name).name != name:
            _fail("The workspace versioned-document inventory is unsafe.")
        path = documents / name
        snapshot = _snapshot_bounded_file(
            path,
            "A workspace versioned document",
            MAX_EVIDENCE_DOCUMENT_BYTES,
            require_nonempty=True,
        )
        metadata, parent_chain = workspace_api._lstat_nofollow(path)
        if (
            snapshot["mode"] != 0o600
            or metadata.st_nlink != 1
            or (metadata.st_dev, metadata.st_ino) != snapshot["identity"]
            or parent_chain != snapshot["parent_chain"]
        ):
            _fail("A workspace versioned document is not one private regular file.")
        total += snapshot["bytes"]
        if total > MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES:
            _fail("The workspace versioned-document byte total exceeds its bound.")
    final_directory = workspace_api._snapshot_directory(
        documents, "The workspace versioned-document directory"
    )
    if workspace_api._directory_seal(final_directory) != workspace_api._directory_seal(
        initial_directory
    ):
        _fail("The workspace versioned-document inventory changed while it was counted.")
    return total


def _snapshot_document_source(
    root: Path,
    source_relative: object,
    expected_sha256: object,
    live_workspace: Path,
) -> tuple[Path, Mapping[str, Any]]:
    source_safe = workspace_api._safe_relative(
        source_relative, "private evidence-document source"
    )
    source_path = workspace_api._project_path(
        root, source_safe.as_posix(), "private evidence-document source"
    )
    try:
        source_path.relative_to(live_workspace)
    except ValueError:
        pass
    else:
        _fail("A versioned-document source cannot be inside the live workspace.")
    if (
        not isinstance(expected_sha256, str)
        or workspace_api.SHA256_RE.fullmatch(expected_sha256) is None
        or not workspace_api._git_ignored(root, source_path)
    ):
        _fail("A versioned-document source binding is invalid.")
    initial = _snapshot_bounded_file(
        source_path,
        "A private versioned-document source",
        MAX_EVIDENCE_DOCUMENT_BYTES,
        require_nonempty=True,
    )
    source_metadata, source_parent_chain = workspace_api._lstat_nofollow(source_path)
    if (
        initial["mode"] != 0o600
        or initial["sha256"] != expected_sha256
        or source_metadata.st_nlink != 1
        or (source_metadata.st_dev, source_metadata.st_ino) != initial["identity"]
        or source_parent_chain != initial["parent_chain"]
    ):
        _fail("A private versioned document differs from its human-supplied binding.")
    return source_path, initial


def _copy_document(
    root: Path,
    source_path: Path,
    initial: Mapping[str, Any],
    stage_fd: int,
    destination_relative: str,
) -> int:
    source_parent, source_name, source_chain = workspace_api._open_parent_fd(source_path)
    destination_parent, destination_name = _relative_parent_fd(
        stage_fd, Path(destination_relative)
    )
    try:
        current = os.stat(source_name, dir_fd=source_parent, follow_symlinks=False)
        if (
            source_chain != initial["parent_chain"]
            or not stat.S_ISREG(current.st_mode)
            or stat.S_IMODE(current.st_mode) != 0o600
            or current.st_nlink != 1
            or (current.st_dev, current.st_ino) != initial["identity"]
            or current.st_size != initial["bytes"]
        ):
            _fail("A private versioned document changed before import.")
        _copy_regular_file(
            source_parent, source_name, destination_parent, destination_name
        )
        os.fsync(destination_parent)
    finally:
        os.close(destination_parent)
        os.close(source_parent)
    final = _snapshot_bounded_file(
        source_path,
        "A private versioned-document source",
        MAX_EVIDENCE_DOCUMENT_BYTES,
        require_nonempty=True,
    )
    final_metadata, final_parent_chain = workspace_api._lstat_nofollow(source_path)
    if (
        workspace_api._seal(final) != workspace_api._seal(initial)
        or final["parent_chain"] != source_chain
        or final_parent_chain != source_chain
        or final_metadata.st_nlink != 1
        or (final_metadata.st_dev, final_metadata.st_ino) != final["identity"]
        or not workspace_api._git_ignored(root, source_path)
    ):
        _fail("A private versioned document changed during import.")
    return final["bytes"]


def _preflight_document_additions(
    root: Path,
    additions: Sequence[object],
    live_workspace: Path,
) -> tuple[dict[int, tuple[Path, Mapping[str, Any]]], int]:
    prepared: dict[int, tuple[Path, Mapping[str, Any]]] = {}
    total = 0
    for index, raw in enumerate(additions):
        if not isinstance(raw, Mapping) or raw.get("namespace") != "versioned_document":
            continue
        operation = _exact(
            raw, DOCUMENT_EVIDENCE_FIELDS, "A versioned-document evidence addition"
        )
        _bounded_text(operation["document_version"], "document version", 1024)
        _strict_utc(operation["accessed_at_utc"], "document access time")
        source_path, snapshot = _snapshot_document_source(
            root,
            operation["source_private_path"],
            operation["expected_document_sha256"],
            live_workspace,
        )
        total += snapshot["bytes"]
        if total > MAX_IMPORTED_DOCUMENT_BYTES_PER_TRANSACTION:
            _fail("The transaction's imported-document byte total exceeds its bound.")
        prepared[index] = (source_path, snapshot)
    return prepared, total


def _active_by_id(records: Sequence[Mapping[str, Any]], key: str) -> dict[str, Mapping[str, Any]]:
    active: dict[str, Mapping[str, Any]] = {}
    for record in records[1:]:
        identifier = record.get(key)
        if isinstance(identifier, str):
            active[identifier] = record
    return active


def _existing_reviewer(stage: Path, batch_count: int) -> str | None:
    reviewers: set[str] = set()
    paths = [
        *(stage / f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
          for index in range(1, batch_count + 1)),
        stage / "route-decisions/route-decisions-batch-0001.jsonl",
        stage / "semantic-groups/mapping-groups.jsonl",
        stage / "attestations/batch-attestations.jsonl",
    ]
    for path in paths:
        for record in _read_records(path, "A staged human ledger")[1:]:
            value = record.get("reviewer_id")
            if isinstance(value, str) and value:
                reviewers.add(value)
    if len(reviewers) > 1:
        _fail("The staged workspace already violates the single-reviewer contract.")
    return next(iter(reviewers)) if reviewers else None


def _registry_map(records: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    return {
        record["evidence_id"]: {
            "namespace": record["namespace"],
            "locator": record["locator"],
        }
        for record in records[1:]
    }


def _latest_event_time(records: Sequence[Mapping[str, Any]]) -> datetime | None:
    if len(records) == 1:
        return None
    value = records[-1].get("event_at_utc") or records[-1].get("recorded_at_utc")
    return _utc(value) if isinstance(value, str) and workspace_api._strict_utc(value) else None


def _make_revision_event(
    records: list[Mapping[str, Any]],
    *,
    revision_kind: str,
    subject_id: str,
    batch_index: int | None,
    revision: int,
    revision_record: Mapping[str, Any],
    reviewer: str,
    recorded_at: str,
) -> Mapping[str, Any]:
    record = {
        "record_type": "revision_event",
        "event_index": len(records),
        "previous_event_sha256": (
            None if len(records) == 1 else workspace_api._record_sha(records[-1])
        ),
        "revision_kind": revision_kind,
        "subject_id": subject_id,
        "batch_index": batch_index,
        "revision": revision,
        "revision_sha256": workspace_api._record_sha(revision_record),
        "supersedes_sha256": revision_record["supersedes_sha256"],
        "reviewer_id": reviewer,
        "recorded_at_utc": recorded_at,
    }
    records.append(record)
    return record


def _make_workspace_event(
    records: list[Mapping[str, Any]],
    *,
    event_type: str,
    event_at: str,
    actor: str,
    subject_kind: str,
    subject_id: str,
    subject_sha256: str,
) -> Mapping[str, Any]:
    record = {
        "record_type": "workspace_event",
        "event_index": len(records),
        "previous_event_sha256": (
            None if len(records) == 1 else workspace_api._record_sha(records[-1])
        ),
        "event_type": event_type,
        "event_at_utc": event_at,
        "actor_id": actor,
        "subject_kind": subject_kind,
        "subject_id": subject_id,
        "subject_sha256": subject_sha256,
    }
    records.append(record)
    return record


def _ensure_event_time(last: datetime | None, value: str, submitted: str) -> datetime:
    current = _utc(value)
    if (last is not None and current < last) or current > _utc(submitted):
        _fail("Human-supplied operation times are not monotone and bounded by submission time.")
    return current


def _prepare_evidence(
    root: Path,
    stage_fd: int,
    additions: Sequence[object],
    existing_records: list[Mapping[str, Any]],
    document_preflights: Mapping[int, tuple[Path, Mapping[str, Any]]],
) -> tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]], int, int]:
    registry = _registry_map(existing_records)
    output: list[Mapping[str, Any]] = []
    previous = existing_records[-1].get("evidence_id") if len(existing_records) > 1 else None
    seen: set[str] = set()
    imported_document_bytes = 0
    for addition_index, raw in enumerate(additions):
        if not isinstance(raw, Mapping):
            _fail("An evidence addition is not an object.")
        namespace = raw.get("namespace")
        fields = DOCUMENT_EVIDENCE_FIELDS if namespace == "versioned_document" else LOCAL_OR_TEMPLATE_EVIDENCE_FIELDS
        operation = _exact(raw, fields, "An evidence addition")
        evidence_id = operation["evidence_id"]
        if (
            not isinstance(evidence_id, str)
            or workspace_api.EVIDENCE_ID_RE.fullmatch(evidence_id) is None
            or evidence_id in seen
            or evidence_id in registry
            or (isinstance(previous, str) and evidence_id <= previous)
        ):
            _fail("An evidence addition has a duplicate or out-of-order identity.")
        seen.add(evidence_id)
        previous = evidence_id
        if namespace == "versioned_document":
            version = _bounded_text(operation["document_version"], "document version", 1024)
            accessed = _strict_utc(operation["accessed_at_utc"], "document access time")
            destination = f"evidence-registry/documents/{evidence_id}.document"
            preflight = document_preflights.get(addition_index)
            if preflight is None:
                _fail("A versioned-document evidence addition lacks a closed preflight.")
            source_path, initial = preflight
            imported_document_bytes += _copy_document(
                root,
                source_path,
                initial,
                stage_fd,
                destination,
            )
            if imported_document_bytes > MAX_IMPORTED_DOCUMENT_BYTES_PER_TRANSACTION:
                _fail("The imported-document byte total changed beyond its bound.")
            locator = {
                "evidence_id": evidence_id,
                "document_sha256": operation["expected_document_sha256"],
                "document_version": version,
                "accessed_at_utc": accessed,
                "private_local_path": destination,
            }
        elif namespace in {"local_tuple", "source_template"}:
            if not isinstance(operation["locator"], Mapping):
                _fail("An evidence locator is not an object.")
            locator = dict(operation["locator"])
        else:
            _fail("An evidence addition uses an unsupported namespace.")
        record = {
            "record_type": "evidence_registry_entry",
            "evidence_id": evidence_id,
            "namespace": namespace,
            "locator": locator,
        }
        output.append(record)
        registry[evidence_id] = {"namespace": namespace, "locator": locator}
    _append_records(
        stage_fd, "evidence-registry/evidence-registry.jsonl", output
    )
    return output, registry, len(output), imported_document_bytes


def _batch_index(review_id: str, batch_size: int) -> int:
    return (int(review_id[1:]) - 1) // batch_size + 1


def _post_batch_bindings(
    stage: Path, batch_count: int
) -> tuple[
    dict[tuple[str, int], dict[str, Any]],
    dict[tuple[str, int], dict[str, Mapping[str, Any]]],
]:
    bindings: dict[tuple[str, int], dict[str, Any]] = {}
    active_sets: dict[tuple[str, int], dict[str, Mapping[str, Any]]] = {}
    for kind, count in (("semantic", batch_count), ("route", 1)):
        for index in range(1, count + 1):
            relative = (
                f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
                if kind == "semantic"
                else "route-decisions/route-decisions-batch-0001.jsonl"
            )
            path = stage / relative
            records = _read_records(path, "A staged decision ledger")
            active = _active_by_id(records, "review_id")
            snapshot = workspace_api._snapshot_file(path, "A staged decision ledger")
            bindings[(kind, index)] = {
                "item_count": len(active),
                "active_hash": workspace_api._active_batch_hash(kind, index, active),
                "ledger_sha256": snapshot["sha256"],
            }
            active_sets[(kind, index)] = active
    return bindings, active_sets


def _current_attestations(
    records: Sequence[Mapping[str, Any]],
    bindings: Mapping[tuple[str, int], Mapping[str, Any]],
    group_sha: str,
) -> dict[tuple[str, int], str]:
    current: dict[tuple[str, int], str] = {}
    for record in records[1:]:
        key = (record["review_kind"], record["batch_index"])
        binding = bindings.get(key)
        expected_group = group_sha if key[0] == "semantic" else None
        if binding is not None and (
            record["item_count"] == binding["item_count"]
            and record["active_decisions_sha256"] == binding["active_hash"]
            and record["decision_ledger_sha256"] == binding["ledger_sha256"]
            and record["mapping_group_registry_sha256"] == expected_group
        ):
            digest = workspace_api._record_sha(record)
            if key in current and current[key] != digest:
                _fail("A batch already has multiple current attestations.")
            current[key] = digest
    return current


def _apply_to_stage(
    root: Path,
    stage_relative: Path,
    stage_fd: int,
    reviewer: str,
    operations: Mapping[str, Any],
    contract: Mapping[str, Any],
    document_preflights: Mapping[int, tuple[Path, Mapping[str, Any]]],
    expected_existing_document_bytes: int,
    expected_imported_document_bytes: int,
) -> dict[str, Any]:
    stage = root / stage_relative
    batch_count = contract["config"]["workspace"]["semantic_batch_count"]
    batch_size = contract["config"]["workspace"]["semantic_batch_size"]
    existing_reviewer = _existing_reviewer(stage, batch_count)
    if existing_reviewer is not None and existing_reviewer != reviewer:
        _fail("The transaction reviewer differs from the workspace reviewer.")

    stage_existing_document_bytes = _versioned_document_total(stage)
    if (
        stage_existing_document_bytes != expected_existing_document_bytes
        or stage_existing_document_bytes + expected_imported_document_bytes
        > MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES
    ):
        _fail("The staged versioned-document byte total changed before import.")

    evidence_path = stage / "evidence-registry/evidence-registry.jsonl"
    evidence_records = _read_records(evidence_path, "The staged evidence registry")
    _, evidence_registry, evidence_count, imported_document_bytes = _prepare_evidence(
        root,
        stage_fd,
        operations["evidence_additions"],
        evidence_records,
        document_preflights,
    )
    final_document_bytes = _versioned_document_total(stage)
    if (
        imported_document_bytes != expected_imported_document_bytes
        or final_document_bytes
        != stage_existing_document_bytes + imported_document_bytes
        or final_document_bytes > MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES
    ):
        _fail("The staged versioned-document byte totals failed conservation.")

    revision_event_path = stage / "revisions/revision-events.jsonl"
    workspace_event_path = stage / "workspace-events.jsonl"
    revision_events = _read_records(revision_event_path, "The staged revision-event ledger")
    workspace_events = _read_records(workspace_event_path, "The staged workspace-event ledger")
    new_revision_events: list[Mapping[str, Any]] = []
    new_workspace_events: list[Mapping[str, Any]] = []
    revision_last_time = _latest_event_time(revision_events)
    workspace_last_time = _latest_event_time(workspace_events)
    submitted = operations["_submitted_at_utc"]

    semantic_ops: dict[str, Mapping[str, Any]] = {}
    semantic_records_to_append: dict[int, list[Mapping[str, Any]]] = {}
    semantic_active: dict[str, Mapping[str, Any]] = {}
    for index in range(1, batch_count + 1):
        path = stage / f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl"
        semantic_active.update(_active_by_id(_read_records(path, "A staged semantic ledger"), "review_id"))
    for raw in operations["semantic_revisions"]:
        operation = _exact(raw, SEMANTIC_OPERATION_FIELDS, "A semantic revision operation")
        review_id = operation["review_id"]
        if (
            not isinstance(review_id, str)
            or workspace_api.SEMANTIC_ID_RE.fullmatch(review_id) is None
            or review_id not in semantic_active
            or review_id in semantic_ops
        ):
            _fail("A semantic revision operation has an invalid or duplicate identity.")
        semantic_ops[review_id] = operation
        if operation["review_status"] != "reviewed":
            _fail("A semantic revision lacks an explicit human-reviewed state.")
        reviewed_at = _strict_utc(operation["reviewed_at_utc"], "semantic review time")
        revision_last_time = _ensure_event_time(revision_last_time, reviewed_at, submitted)
        workspace_last_time = _ensure_event_time(workspace_last_time, reviewed_at, submitted)
        predecessor = semantic_active[review_id]
        record = {
            "record_type": "semantic_decision_revision",
            "review_id": review_id,
            "revision": predecessor["revision"] + 1,
            "supersedes_sha256": workspace_api._record_sha(predecessor),
            "revision_reason": operation["revision_reason"],
            "review_status": operation["review_status"],
            "dimensions": operation["dimensions"],
            "mapping_group_id": operation["mapping_group_id"],
            "rationale": operation["rationale"],
            "reviewer_id": reviewer,
            "reviewed_at_utc": reviewed_at,
        }
        try:
            workspace_api._validate_semantic_revision(
                record, contract["config"]["semantic_review"], evidence_registry
            )
        except workspace_api.HumanAdjudicationError as error:
            raise HumanAdjudicationWriterError(str(error)) from None
        index = _batch_index(review_id, batch_size)
        semantic_records_to_append.setdefault(index, []).append(record)
        semantic_active[review_id] = record
        revision_event = _make_revision_event(
            revision_events,
            revision_kind="semantic_decision",
            subject_id=review_id,
            batch_index=index,
            revision=record["revision"],
            revision_record=record,
            reviewer=reviewer,
            recorded_at=reviewed_at,
        )
        new_revision_events.append(revision_event)
        event = _make_workspace_event(
            workspace_events,
            event_type="batch_submitted" if record["revision"] == 2 else "batch_revised",
            event_at=reviewed_at,
            actor=reviewer,
            subject_kind="revision_event",
            subject_id=workspace_api._revision_event_subject(revision_event),
            subject_sha256=workspace_api._record_sha(revision_event),
        )
        new_workspace_events.append(event)

    route_path = stage / "route-decisions/route-decisions-batch-0001.jsonl"
    route_active = _active_by_id(_read_records(route_path, "The staged route ledger"), "review_id")
    route_seen: set[str] = set()
    route_output: list[Mapping[str, Any]] = []
    for raw in operations["route_revisions"]:
        operation = _exact(raw, ROUTE_OPERATION_FIELDS, "A route revision operation")
        review_id = operation["review_id"]
        if (
            not isinstance(review_id, str)
            or workspace_api.ROUTE_ID_RE.fullmatch(review_id) is None
            or review_id not in route_active
            or review_id in route_seen
        ):
            _fail("A route revision operation has an invalid or duplicate identity.")
        route_seen.add(review_id)
        if operation["review_status"] != "reviewed":
            _fail("A route revision lacks an explicit human-reviewed state.")
        reviewed_at = _strict_utc(operation["reviewed_at_utc"], "route review time")
        revision_last_time = _ensure_event_time(revision_last_time, reviewed_at, submitted)
        workspace_last_time = _ensure_event_time(workspace_last_time, reviewed_at, submitted)
        predecessor = route_active[review_id]
        record = {
            "record_type": "route_decision_revision",
            "review_id": review_id,
            "revision": predecessor["revision"] + 1,
            "supersedes_sha256": workspace_api._record_sha(predecessor),
            "revision_reason": operation["revision_reason"],
            "review_status": operation["review_status"],
            "decision": operation["decision"],
            "decision_basis": operation["decision_basis"],
            "evidence_refs": operation["evidence_refs"],
            "rationale": operation["rationale"],
            "reviewer_id": reviewer,
            "reviewed_at_utc": reviewed_at,
        }
        try:
            workspace_api._validate_route_revision(record, evidence_registry)
        except workspace_api.HumanAdjudicationError as error:
            raise HumanAdjudicationWriterError(str(error)) from None
        route_output.append(record)
        route_active[review_id] = record
        revision_event = _make_revision_event(
            revision_events,
            revision_kind="route_decision",
            subject_id=review_id,
            batch_index=1,
            revision=record["revision"],
            revision_record=record,
            reviewer=reviewer,
            recorded_at=reviewed_at,
        )
        new_revision_events.append(revision_event)
        event = _make_workspace_event(
            workspace_events,
            event_type="batch_submitted" if record["revision"] == 2 else "batch_revised",
            event_at=reviewed_at,
            actor=reviewer,
            subject_kind="revision_event",
            subject_id=workspace_api._revision_event_subject(revision_event),
            subject_sha256=workspace_api._record_sha(revision_event),
        )
        new_workspace_events.append(event)

    group_path = stage / "semantic-groups/mapping-groups.jsonl"
    group_records = _read_records(group_path, "The staged mapping-group ledger")
    group_active = _active_by_id(group_records, "mapping_group_id")
    group_previous_members = {
        key: set(value["member_review_ids"]) for key, value in group_active.items()
    }
    group_seen: set[str] = set()
    group_output: list[Mapping[str, Any]] = []
    for raw in operations["mapping_group_revisions"]:
        operation = _exact(raw, GROUP_OPERATION_FIELDS, "A mapping-group revision operation")
        group_id = operation["mapping_group_id"]
        if (
            not isinstance(group_id, str)
            or workspace_api.GROUP_ID_RE.fullmatch(group_id) is None
            or group_id in group_seen
        ):
            _fail("A mapping-group revision has an invalid or duplicate identity.")
        group_seen.add(group_id)
        if operation["review_status"] != "reviewed":
            _fail("A mapping-group revision lacks an explicit human-reviewed state.")
        reviewed_at = _strict_utc(operation["reviewed_at_utc"], "mapping-group review time")
        revision_last_time = _ensure_event_time(revision_last_time, reviewed_at, submitted)
        workspace_last_time = _ensure_event_time(workspace_last_time, reviewed_at, submitted)
        predecessor = group_active.get(group_id)
        record = {
            "record_type": "mapping_group_revision",
            "mapping_group_id": group_id,
            "revision": 1 if predecessor is None else predecessor["revision"] + 1,
            "supersedes_sha256": None if predecessor is None else workspace_api._record_sha(predecessor),
            "revision_reason": operation["revision_reason"],
            "review_status": operation["review_status"],
            "member_review_ids": operation["member_review_ids"],
            "local_evidence_refs": operation["local_evidence_refs"],
            "dimensions": operation["dimensions"],
            "rationale": operation["rationale"],
            "reviewer_id": reviewer,
            "reviewed_at_utc": reviewed_at,
        }
        # Exact group/local-tuple linkage is checked by the full staged validator.
        if not isinstance(record["member_review_ids"], list) or not isinstance(record["local_evidence_refs"], list):
            _fail("A mapping-group revision has invalid collection fields.")
        _bounded_text(record["revision_reason"], "mapping-group revision reason")
        _bounded_text(record["rationale"], "mapping-group rationale")
        group_output.append(record)
        group_active[group_id] = record
        revision_event = _make_revision_event(
            revision_events,
            revision_kind="mapping_group",
            subject_id=group_id,
            batch_index=None,
            revision=record["revision"],
            revision_record=record,
            reviewer=reviewer,
            recorded_at=reviewed_at,
        )
        new_revision_events.append(revision_event)
        event = _make_workspace_event(
            workspace_events,
            event_type="group_registry_revised",
            event_at=reviewed_at,
            actor=reviewer,
            subject_kind="revision_event",
            subject_id=workspace_api._revision_event_subject(revision_event),
            subject_sha256=workspace_api._record_sha(revision_event),
        )
        new_workspace_events.append(event)

    # A membership change and every affected member decision are one transaction.
    for group_id in group_seen:
        old = group_previous_members.get(group_id, set())
        new = set(group_active[group_id]["member_review_ids"])
        if old != new and not (old | new).issubset(semantic_ops):
            _fail("A mapping-group membership change lacks atomic member revisions.")
    assignments: dict[str, set[str]] = {}
    for review_id, record in semantic_active.items():
        group_id = record.get("mapping_group_id")
        if group_id is not None:
            assignments.setdefault(group_id, set()).add(review_id)
    if set(assignments) != set(group_active) or any(
        assignments[group_id] != set(record["member_review_ids"])
        for group_id, record in group_active.items()
    ):
        _fail("The proposed semantic assignments and mapping-group registry differ.")

    for index, records in semantic_records_to_append.items():
        _append_records(
            stage_fd,
            f"semantic-decisions/semantic-decisions-batch-{index:04d}.jsonl",
            records,
        )
    _append_records(stage_fd, "route-decisions/route-decisions-batch-0001.jsonl", route_output)
    _append_records(stage_fd, "semantic-groups/mapping-groups.jsonl", group_output)
    _append_records(stage_fd, "revisions/revision-events.jsonl", new_revision_events)
    _append_records(stage_fd, "workspace-events.jsonl", new_workspace_events)

    batch_bindings, active_sets = _post_batch_bindings(stage, batch_count)
    group_sha = workspace_api._snapshot_file(
        group_path, "The staged mapping-group ledger"
    )["sha256"]
    attestation_path = stage / "attestations/batch-attestations.jsonl"
    attestation_records = _read_records(attestation_path, "The staged attestation ledger")
    current = _current_attestations(attestation_records, batch_bindings, group_sha)
    attestation_output: list[Mapping[str, Any]] = []
    attestation_seen: set[tuple[str, int]] = set()
    for raw in operations["attestations"]:
        operation = _exact(raw, ATTESTATION_OPERATION_FIELDS, "A batch-attestation operation")
        kind = operation["review_kind"]
        index = operation["batch_index"]
        key = (kind, index)
        if (
            kind not in {"semantic", "route"}
            or type(index) is not int
            or key not in batch_bindings
            or key in attestation_seen
            or key in current
            or operation["attestation_method"] != "human"
            or operation["confirm_complete"] is not True
            or operation["confirm_review_policy_version"] != contract["config"]["rule_version"]
            or not all(record.get("review_status") == "reviewed" for record in active_sets[key].values())
        ):
            _fail("A human batch-attestation operation is invalid or not complete.")
        attestation_seen.add(key)
        attested_at = _strict_utc(operation["attested_at_utc"], "batch attestation time")
        workspace_last_time = _ensure_event_time(workspace_last_time, attested_at, submitted)
        binding = batch_bindings[key]
        record = {
            "record_type": "batch_attestation",
            "review_kind": kind,
            "batch_index": index,
            "item_count": binding["item_count"],
            "active_decisions_sha256": binding["active_hash"],
            "decision_ledger_sha256": binding["ledger_sha256"],
            "mapping_group_registry_sha256": group_sha if kind == "semantic" else None,
            "review_policy_version": contract["config"]["rule_version"],
            "attestation_method": "human",
            "reviewer_id": reviewer,
            "attested_at_utc": attested_at,
        }
        attestation_output.append(record)
        attestation_records.append(record)
        digest = workspace_api._record_sha(record)
        current[key] = digest
        event = _make_workspace_event(
            workspace_events,
            event_type="attestation_added",
            event_at=attested_at,
            actor=reviewer,
            subject_kind="batch_attestation",
            subject_id=workspace_api._attestation_event_subject(record),
            subject_sha256=digest,
        )
        _append_records(stage_fd, "workspace-events.jsonl", [event])
    _append_records(stage_fd, "attestations/batch-attestations.jsonl", attestation_output)

    terminal = operations["terminal_event"]
    terminal_type: str | None = None
    if terminal is not None:
        terminal_type = terminal.get("event_type")
        if terminal_type == "human_review_complete_unfrozen":
            terminal = _exact(terminal, COMPLETION_FIELDS, "The completion operation")
            if terminal["confirm_all_batches_complete"] is not True:
                _fail("The human completion confirmation is absent.")
            if not all(
                all(record.get("review_status") == "reviewed" for record in active.values())
                for active in active_sets.values()
            ) or set(current) != set(batch_bindings):
                _fail("The workspace is not complete and currently attested.")
            event_at = _strict_utc(terminal["event_at_utc"], "completion time")
            workspace_last_time = _ensure_event_time(workspace_last_time, event_at, submitted)
            active_groups = _active_by_id(
                _read_records(group_path, "The staged mapping-group ledger"),
                "mapping_group_id",
            )
            state_hash = workspace_api._active_workspace_state_hash(
                batch_bindings, active_groups, current
            )
            event = _make_workspace_event(
                workspace_events,
                event_type=terminal_type,
                event_at=event_at,
                actor=reviewer,
                subject_kind="active_workspace_state",
                subject_id=COMPONENT_ID,
                subject_sha256=state_hash,
            )
            _append_records(stage_fd, "workspace-events.jsonl", [event])
        elif terminal_type == "abandoned":
            terminal = _exact(terminal, ABANDON_FIELDS, "The abandonment operation")
            if any(operations[key] for key in OPERATION_FIELDS - {"terminal_event"}):
                _fail("Abandonment must be the only operation in its transaction.")
            _bounded_text(terminal["reason"], "abandonment reason")
            event_at = _strict_utc(terminal["event_at_utc"], "abandonment time")
            workspace_last_time = _ensure_event_time(workspace_last_time, event_at, submitted)
            event = _make_workspace_event(
                workspace_events,
                event_type="abandoned",
                event_at=event_at,
                actor=reviewer,
                subject_kind="component_config",
                subject_id=COMPONENT_ID,
                subject_sha256=contract["config_sha256"],
            )
            _append_records(stage_fd, "workspace-events.jsonl", [event])
        else:
            _fail("The terminal operation type is unsupported.")

    os.fsync(stage_fd)
    return {
        "evidence_additions": evidence_count,
        "semantic_revisions": len(semantic_ops),
        "route_revisions": len(route_seen),
        "mapping_group_revisions": len(group_seen),
        "attestations": len(attestation_seen),
        "terminal_event": terminal_type,
    }


def _exchange_directories(parent_fd: int, left: str, right: str) -> None:
    library = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        function = getattr(library, "renameatx_np", None)
    elif sys.platform.startswith("linux"):
        function = getattr(library, "renameat2", None)
    else:
        function = None
    if function is None:
        _fail("This platform lacks atomic directory exchange.")
    function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    function.restype = ctypes.c_int
    ctypes.set_errno(0)
    result = function(
        parent_fd,
        os.fsencode(left),
        parent_fd,
        os.fsencode(right),
        0x00000002,  # RENAME_SWAP / RENAME_EXCHANGE
    )
    if result != 0:
        code = ctypes.get_errno()
        if code in {errno.ENOSYS, errno.EINVAL, errno.ENOTSUP, errno.EXDEV}:
            _fail("Atomic directory exchange is unavailable on this filesystem.")
        raise OSError(code, os.strerror(code))


def _named_identity(parent_fd: int, name: str) -> tuple[int, int]:
    metadata = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(metadata.st_mode):
        _fail("An exchanged workspace leaf is not a real directory.")
    return metadata.st_dev, metadata.st_ino


def _recover_stale_stages(
    root: Path,
    workspace_relative: Path,
    config_path: Path,
    parent_fd: int,
    parent_chain: tuple[tuple[int, int], ...],
) -> Mapping[str, Any] | None:
    """Recover only states made unambiguous by the atomically named live tree.

    If the named live workspace validates, it is authoritative and every stale
    sibling is an unpublished candidate or the old side of a committed swap.
    If it does not validate, the live and stale trees are retained for manual
    inspection.  A stale sibling can be either an unpublished candidate or the
    old side of a committed exchange, so its mere validity is not enough to
    choose a state without a durable phase journal.
    """
    prefix = f"{STAGE_PREFIX}{workspace_relative.name}-"
    stale_names = sorted(
        name for name in os.listdir(parent_fd) if name.startswith(prefix)
    )
    if not stale_names:
        return None
    live_report: Mapping[str, Any] | None = None
    try:
        live_report = workspace_api.validate_human_adjudication_workspace(
            root, workspace_relative, config_path=config_path
        )
    except (workspace_api.HumanAdjudicationError, OSError, ValueError):
        pass
    if live_report is not None:
        for name in stale_names:
            identity = _named_identity(parent_fd, name)
            workspace_api._remove_tree_if_identity_at(parent_fd, name, identity)
        os.fsync(parent_fd)
        return live_report
    _fail(
        "The live workspace is invalid while a stale authoring stage exists; "
        "both states were retained for manual recovery."
    )


def _assert_transaction_closure(root: Path, snapshot: Mapping[str, Any]) -> None:
    final = _snapshot_bounded_file(
        snapshot["path"],
        "The private authoring transaction",
        MAX_TRANSACTION_BYTES,
    )
    metadata, parent_chain = workspace_api._lstat_nofollow(snapshot["path"])
    if (
        workspace_api._seal(final) != workspace_api._seal(snapshot)
        or parent_chain != final["parent_chain"]
        or metadata.st_nlink != 1
        or (metadata.st_dev, metadata.st_ino) != final["identity"]
        or final["mode"] != 0o600
        or final["bytes"] > MAX_TRANSACTION_BYTES
        or not workspace_api._git_ignored(root, snapshot["path"])
    ):
        _fail("The private authoring transaction changed while it was applied.")


def apply_human_adjudication_transaction(
    root: Path,
    transaction_path: Path,
    config_path: Path = CONFIG_PATH,
) -> dict[str, Any]:
    """Apply one exact human-authored transaction by validated atomic exchange."""
    root = root.resolve(strict=True)
    transaction, transaction_snapshot = _load_private_transaction(root, transaction_path)
    workspace_relative, expected_hash, reviewer, operations = _validate_transaction_envelope(transaction)
    live_workspace = workspace_api._project_path(
        root, workspace_relative.as_posix(), "human-adjudication workspace"
    )
    try:
        transaction_snapshot["path"].relative_to(live_workspace)
    except ValueError:
        pass
    else:
        _fail("The transaction file cannot be stored inside the workspace it updates.")

    parent_fd, lock_fd, lock_name, parent_chain = _acquire_lock(root, workspace_relative)
    stage_name: str | None = None
    stage_fd: int | None = None
    stage_identity: tuple[int, int] | None = None
    live_identity: tuple[int, int] | None = None
    exchanged = False
    committed = False
    try:
        # The normal validator supplies formal preregistration readiness and
        # rejects previews, malformed/branched ledgers, and terminal states.
        # Under the external lock, first settle any interrupted prior exchange.
        base_report = _recover_stale_stages(
            root,
            workspace_relative,
            config_path,
            parent_fd,
            parent_chain,
        )
        if base_report is None:
            base_report = workspace_api.validate_human_adjudication_workspace(
                root, workspace_relative, config_path=config_path
            )
        if (
            not base_report.get("valid")
            or base_report.get("formal_workspace") is not True
            or base_report.get("status") not in {"initialized", "review_in_progress"}
            or base_report.get("reviewed_semantic_ledger_frozen") is not False
            or base_report.get("route_mapping_frozen") is not False
        ):
            _fail("The workspace lifecycle does not permit an authoring transaction.")
        base_hash, live_identity, live_parent_chain = _workspace_snapshot_hash(live_workspace)
        if base_hash != expected_hash:
            _fail("The transaction is stale for the current workspace snapshot.")
        if live_parent_chain[:-1] != parent_chain:
            _fail("The workspace parent changed before staging.")
        contract = workspace_api._load_contract(
            root, config_path, allow_proposed=False
        )
        existing_document_bytes = _versioned_document_total(live_workspace)
        document_preflights, imported_document_bytes = _preflight_document_additions(
            root,
            operations["evidence_additions"],
            live_workspace,
        )
        if (
            existing_document_bytes + imported_document_bytes
            > MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES
        ):
            _fail("The resulting workspace versioned-document bytes exceed their bound.")
        _assert_transaction_closure(root, transaction_snapshot)
        stage_name, stage_fd, stage_identity = _stage_workspace(
            parent_fd, workspace_relative.name
        )
        stage_relative = workspace_relative.parent / stage_name
        counts = _apply_to_stage(
            root,
            stage_relative,
            stage_fd,
            reviewer,
            operations,
            contract,
            document_preflights,
            existing_document_bytes,
            imported_document_bytes,
        )
        _inject("before_stage_validation")
        staged_report = workspace_api.validate_human_adjudication_workspace(
            root,
            stage_relative,
            config_path=config_path,
            _logical_workspace_directory=workspace_relative,
        )
        expected_terminal = counts["terminal_event"]
        if expected_terminal == "human_review_complete_unfrozen":
            if staged_report.get("status") != "human_review_complete_unfrozen":
                _fail("The validated staged workspace did not reach human-review completion.")
        elif expected_terminal == "abandoned":
            if staged_report.get("status") != "abandoned":
                _fail("The validated staged workspace did not reach abandonment.")
        elif staged_report.get("status") not in {"initialized", "review_in_progress"}:
            _fail("The validated staged workspace reached an unexpected lifecycle.")
        staged_hash, checked_stage_identity, staged_parent_chain = _workspace_snapshot_hash(
            root / stage_relative
        )
        if checked_stage_identity != stage_identity or staged_parent_chain[:-1] != parent_chain:
            _fail("The staged workspace identity changed before publication.")
        _assert_transaction_closure(root, transaction_snapshot)
        current_hash, checked_live_identity, current_parent_chain = _workspace_snapshot_hash(
            live_workspace
        )
        if (
            current_hash != expected_hash
            or checked_live_identity != live_identity
            or current_parent_chain[:-1] != parent_chain
            or _named_identity(parent_fd, workspace_relative.name) != live_identity
            or _named_identity(parent_fd, stage_name) != stage_identity
        ):
            _fail("The live or staged workspace changed before atomic exchange.")
        fresh_parent_fd, fresh_parent_chain = workspace_api._open_directory_fd(
            root / workspace_relative.parent
        )
        os.close(fresh_parent_fd)
        if fresh_parent_chain != parent_chain:
            _fail("The workspace parent path changed before atomic exchange.")
        _inject("before_exchange")
        _assert_lock_closure(parent_fd, lock_fd, lock_name)
        _exchange_directories(parent_fd, workspace_relative.name, stage_name)
        exchanged = True
        os.fsync(parent_fd)
        _inject("after_exchange")
        if (
            _named_identity(parent_fd, workspace_relative.name) != stage_identity
            or _named_identity(parent_fd, stage_name) != live_identity
        ):
            _fail("The atomic workspace exchange did not preserve both identities.")
        published_hash, published_identity, published_parent_chain = _workspace_snapshot_hash(
            live_workspace
        )
        if (
            published_hash != staged_hash
            or published_identity != stage_identity
            or published_parent_chain[:-1] != parent_chain
        ):
            _fail("The published workspace differs from its validated staged snapshot.")
        _assert_transaction_closure(root, transaction_snapshot)
        _assert_lock_closure(parent_fd, lock_fd, lock_name)
        committed = True
        cleanup_pending = False
        try:
            _inject("before_old_workspace_cleanup")
            workspace_api._remove_tree_if_identity_at(
                parent_fd, stage_name, live_identity
            )
            os.fsync(parent_fd)
        except OSError:
            # Publication is already a validated atomic commit.  The old tree
            # remains a private, identity-bound recovery sibling and is removed
            # by the next locked invocation.
            cleanup_pending = True
        return {
            "status": staged_report["status"],
            "workspace": workspace_relative.as_posix(),
            "workspace_snapshot_hash_version": WORKSPACE_SNAPSHOT_HASH_VERSION,
            "workspace_snapshot_sha256": staged_hash,
            "operations_applied": counts,
            "semantic_items": staged_report["semantic_items"],
            "reviewed_semantic_items": staged_report["reviewed_semantic_items"],
            "route_items": staged_report["route_items"],
            "reviewed_route_items": staged_report["reviewed_route_items"],
            "mapping_groups": staged_report["mapping_groups"],
            "old_workspace_cleanup_pending": cleanup_pending,
            "database_connected": False,
            "external_api_called": False,
            "llm_called": False,
        }
    except BaseException:
        if exchanged and not committed and stage_name is not None:
            try:
                if (
                    stage_identity is not None
                    and live_identity is not None
                    and _named_identity(parent_fd, workspace_relative.name) == stage_identity
                    and _named_identity(parent_fd, stage_name) == live_identity
                ):
                    _exchange_directories(parent_fd, workspace_relative.name, stage_name)
                    exchanged = False
                    os.fsync(parent_fd)
            except BaseException:
                # Both directory trees remain named and private.  A later run
                # fails on the stale stage instead of guessing which one wins.
                pass
        if stage_name is not None and not exchanged:
            try:
                identity = stage_identity
                if identity is not None:
                    workspace_api._remove_tree_if_identity_at(
                        parent_fd, stage_name, identity
                    )
            except OSError:
                pass
        raise
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)
            os.close(parent_fd)


__all__ = [
    "CONFIG_PATH",
    "COMPONENT_ID",
    "HumanAdjudicationWriterError",
    "MAX_EVIDENCE_DOCUMENT_BYTES",
    "MAX_IMPORTED_DOCUMENT_BYTES_PER_TRANSACTION",
    "MAX_TRANSACTION_BYTES",
    "MAX_WORKSPACE_VERSIONED_DOCUMENT_BYTES",
    "TRANSACTION_SCHEMA_VERSION",
    "TRANSACTION_TYPE",
    "WORKSPACE_SNAPSHOT_HASH_VERSION",
    "apply_human_adjudication_transaction",
    "inspect_human_adjudication_workspace",
]
