#!/usr/bin/env python3
"""Check a data-free public worktree before staging/pushing; stdlib only.

This checks paths, known literal secrets, machine-specific locations, and
patient-row keys in serialized reports. It deliberately does not classify
numeric identifiers in Python/SQL synthetic fixtures as patient data. It does
not inspect Git history or infer whether a reviewed PDF contains patient data.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile

VERSION = 'healthcare-ope-public-boundary-v1'
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
DENIED_DIRS = frozenset({'data', 'artifacts', 'private', 'restricted', 'labels', 'draws',
    'cache', 'caches', 'deliverables', 'handoff-work', 'outputs', 'output', '.venv',
    'venv', 'node_modules', '__pycache__', '.aws', '.ssh'})
DENIED_SUFFIXES = frozenset({'.npz', '.npy', '.pkl', '.pickle', '.joblib', '.zip', '.tar',
    '.gz', '.tgz', '.bz2', '.xz', '.zst', '.7z', '.rar', '.parquet', '.feather', '.arrow',
    '.sqlite', '.sqlite3', '.db', '.h5', '.hdf5', '.jsonl', '.ndjson', '.pyc', '.pyo',
    '.pem', '.key', '.p12', '.pfx', '.csv.gz'})
DENIED_NAMES = frozenset({'cases.json', 'credentials', 'credentials.json', 'secrets.json',
    'secrets.toml', 'token.json', 'tokens.json', '.pgpass', '.netrc', '.npmrc', '.pypirc',
    'id_rsa', 'id_ed25519', 'id_ecdsa', 'id_dsa', '.DS_Store'})
TEXT_SUFFIXES = frozenset({'.py', '.sql', '.toml', '.lock', '.md', '.txt', '.rst', '.yml',
    '.yaml', '.json', '.csv', '.tsv', '.svg', '.html', '.css', '.js', '.mjs', '.ini',
    '.cfg', '.sh', '.bib', '.tex', '.in'})
TEXT_NAMES = frozenset({'Makefile', 'LICENSE', 'NOTICE', '.gitignore', '.gitattributes',
    '.editorconfig', 'Dockerfile'})
FIGURE_SUFFIXES = frozenset({'.pdf', '.png', '.jpg', '.jpeg', '.webp'})
PATIENT_KEYS = frozenset({'subject_id', 'subject_ids', 'hadm_id', 'hadm_ids', 'stay_id',
    'stay_ids', 'event_id', 'event_ids', 'request_id', 'request_ids', 'patient_id',
    'patient_ids', 'patient_counts', 'patient_multiplicity', 'population_draw_metadata',
    'annotations', 'raw_prompt', 'raw_response', 'raw_request', 'clinical_notes',
    'draw_id', 'completed_draw_ids', 'draw_annotation_patient_counts'})
# The regex describes home directories without embedding an actual local path.
PERSONAL_PATH = re.compile(rb'(?i)(?:/(?:Users|home|Volumes)/[^\s\"\x27<>${}/]+(?:/|\\)|/(?:root)/[^\s\"\x27<>${}]+|[A-Z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\"\x27<>${}]+)')
# Generic OS temp roots and explicitly synthetic test paths are not private provenance.
TEMP_RUN_PATH = re.compile(rb'/(?:private/)?tmp/[A-Za-z0-9_.-]*(?:20[0-9]{6}|run-[0-9a-f]{8})[A-Za-z0-9_./-]*')
SECRET_PATTERNS = {
    'provider_key': re.compile(rb'(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}'),
    'aws_access_key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'private_key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'github_token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'bearer_literal': re.compile(rb'(?i)Bearer[ \t]+[A-Za-z0-9_.-]{24,}'),
    'credential_assignment': re.compile(rb'(?i)(?<![a-z0-9_])(?:[A-Z0-9_]{0,80}(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|PASSWORD)|api[_-]?key|password)\s*[=:]\s*[\"\x27][A-Za-z0-9_./+\-=]{20,}[\"\x27]'),
}


def patient_key_present(value):
    if isinstance(value, dict):
        return any(str(k).lower() in PATIENT_KEYS or patient_key_present(v) for k, v in value.items())
    if isinstance(value, list):
        return any(patient_key_present(v) for v in value)
    return False


def inspect(root):
    root = root.resolve()
    errors = []
    files = []
    hashes = {}
    binary_figures = []
    total = 0
    if not root.is_dir():
        return {'schema_version': VERSION, 'status': 'failed', 'errors': [{'path': '.', 'reason': 'repository_directory_missing'}]}

    def add(path, reason):
        errors.append({'path': path, 'reason': reason})

    for parent, dirs, names in os.walk(root, followlinks=False):
        for name in list(dirs):
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                add(relative, 'symlink_not_allowed'); dirs.remove(name)
            elif name == '.git':
                dirs.remove(name)
            elif name in DENIED_DIRS:
                add(relative, 'restricted_or_generated_directory'); dirs.remove(name)
        for name in names:
            path = Path(parent) / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink():
                add(relative, 'symlink_not_allowed'); continue
            if not path.is_file():
                add(relative, 'non_regular_file'); continue
            if (name in DENIED_NAMES or name.startswith('.env') or '.local.' in name
                    or path.suffix.lower() in DENIED_SUFFIXES):
                add(relative, 'restricted_file_type_or_name'); continue
            size = path.stat().st_size
            total += size
            if size > MAX_FILE_BYTES:
                add(relative, 'file_exceeds_public_size_limit'); continue
            suffix = path.suffix.lower()
            figure = suffix in FIGURE_SUFFIXES
            text = suffix in TEXT_SUFFIXES or name in TEXT_NAMES
            if not text and not figure:
                add(relative, 'file_type_not_in_public_allowlist'); continue
            if figure and path.relative_to(root).parts[0] not in {'reports', 'figures', 'docs'}:
                add(relative, 'binary_figure_outside_reviewed_report_area'); continue
            if suffix in {'.csv', '.tsv'} and path.relative_to(root).parts[0] != 'reports':
                add(relative, 'tabular_file_outside_aggregate_reports'); continue
            files.append(relative)
            raw = path.read_bytes()
            hashes[relative] = hashlib.sha256(raw).hexdigest()
            if PERSONAL_PATH.search(raw) or TEMP_RUN_PATH.search(raw):
                add(relative, 'machine_specific_absolute_path')
            lower = raw.lower()
            candidates = {
                'provider_key': b'sk-' in raw,
                'aws_access_key': b'AKIA' in raw or b'ASIA' in raw,
                'private_key': b'PRIVATE KEY-----' in raw,
                'github_token': b'gh' in raw or b'github_pat_' in raw,
                'bearer_literal': b'bearer' in lower,
                'credential_assignment': any(s in lower for s in (b'api_key', b'api-key', b'apikey', b'access_token', b'secret_key', b'password')),
            }
            for label, pattern in SECRET_PATTERNS.items():
                if candidates[label] and pattern.search(raw):
                    add(relative, 'literal_secret_pattern_' + label)
            if figure:
                binary_figures.append(relative)
                continue
            try:
                decoded = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                add(relative, 'text_file_is_not_utf8'); continue
            if suffix == '.json':
                try:
                    if patient_key_present(json.loads(decoded)):
                        add(relative, 'patient_or_per_draw_keys_in_serialized_file')
                except (json.JSONDecodeError, RecursionError):
                    add(relative, 'invalid_or_excessively_nested_json')
            elif suffix in {'.csv', '.tsv'}:
                try:
                    rows = csv.reader(io.StringIO(decoded), delimiter='\t' if suffix == '.tsv' else ',')
                    fields = next(rows, [])
                    if any(field.strip().lower() in PATIENT_KEYS for field in fields):
                        add(relative, 'patient_or_per_draw_columns_in_report')
                except csv.Error:
                    add(relative, 'invalid_tabular_report')
    if total > MAX_TOTAL_BYTES:
        add('.', 'repository_exceeds_public_size_limit')
    errors = sorted({(e['path'], e['reason']) for e in errors})
    result = {
        'schema_version': VERSION,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'status': 'passed' if not errors else 'failed',
        'checked_files': len(files),
        'checked_bytes': total,
        'errors': [{'path': p, 'reason': r} for p, r in errors],
        'file_sha256': dict(sorted(hashes.items())),
        'reviewed_binary_figure_paths': sorted(binary_figures),
        'scope': 'Public worktree excluding Git internals; no private bundle or Git-history traversal.',
        'limitations': 'Known secret formats and structural boundaries only; binary figures must already be confirmed aggregate-only. Synthetic identifiers inside source/test code are not treated as patient records.',
        'matched_values_disclosed': False,
        'external_calls': 0,
    }
    return result


def self_test():
    checks = []
    with tempfile.TemporaryDirectory(prefix='public-repo-audit-fixture-') as folder:
        root = Path(folder)
        (root / 'tests').mkdir()
        (root / 'tests/test_fixture.py').write_text("row = {'subject_id': 12345678, 'hadm_id': 98765432}\n")
        assert inspect(root)['status'] == 'passed'; checks.append('synthetic_python_identifiers_allowed')
        cases = [('data/example.csv', b'a,b\n1,2\n'),
                 ('.env', b'EXAMPLE=fixture\n'),
                 ('reports/private.npz', b'fixture'),
                 ('reports/archive.zip', b'fixture'),
                 ('reports/rows.json', b'{"subject_id":12345678}'),
                 ('reports/tokens.txt', ('sk-' + 'A' * 40).encode()),
                 ('README.md', ('/' + 'Users/' + 'fixture-owner/project').encode())]
        for name, content in cases:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
            report = inspect(root)
            assert report['status'] == 'failed' and report['errors']
            assert all(set(e) == {'path', 'reason'} for e in report['errors'])
            path.unlink()
            if path.parent.name == 'data': path.parent.rmdir()
            checks.append('blocked_' + name)
        link = root / 'external-link'; link.symlink_to(Path(folder).parent)
        assert inspect(root)['status'] == 'failed'; link.unlink(); checks.append('symlink_blocked')
        (root / 'reports/aggregate.json').write_text(json.dumps({'rows': [{'model_key': 'fixture', 'target_validation_patients': 15, 'dm_rmse': 0.3}]}))
        assert inspect(root)['status'] == 'passed'; checks.append('aggregate_patient_count_allowed')
    return {'status': 'passed', 'checks': checks, 'private_bundle_read': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repository', type=Path, nargs='?')
    parser.add_argument('--output', type=Path, help='Optional aggregate audit JSON outside the repository')
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False)); return 0
    if args.repository is None:
        parser.error('repository is required unless --self-test is used')
    if args.output and args.output.resolve().is_relative_to(args.repository.resolve()):
        parser.error('write the audit result outside the public repository')
    result = inspect(args.repository)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'checked_files', 'checked_bytes', 'errors') if k in result}, ensure_ascii=False))
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
