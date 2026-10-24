"""Patient bootstrap within fixed train/validation and behavior/target groups.

Patient-cluster resampling is an explicit project choice, not a recovered APRIL
implementation detail. Every selected patient's events carry that patient's
multiplicity. Downstream estimators average repeated events, not patient means.
There is exactly one draw per population/key, even when a rare action is absent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from numbers import Integral
import re

try:
    import numpy as np
except ImportError:
    np = None

from april_repro.clinical_dataset import FOLD_CODES, ROLE_CODES
from april_repro.cohort_splits import ACTIONS, SPLITS


RULE_VERSION = "patient-cluster-bootstrap-v1"
DEFAULT_SEED = "april-cluster-bootstrap-v1"
BOOTSTRAP_REPETITIONS = 500
POPULATIONS = {
    "behavior_train": ("behavior", "train"),
    "target_train": ("target", "train"),
    "target_validation": ("target", "validation"),
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _array_bytes(values):
    return np.asarray(values, dtype="<i8").tobytes(order="C")


@dataclass(frozen=True)
class ClusterDraw:
    event_indices: np.ndarray = field(repr=False)
    subject_ids: np.ndarray = field(repr=False)
    patient_counts: np.ndarray = field(repr=False)
    metadata: dict

    @property
    def status(self):
        return self.metadata["status"]

    @property
    def draw_sha256(self):
        return self.metadata["draw_sha256"]


@dataclass(frozen=True)
class ClusterPopulation:
    task: str
    split: str
    population: str
    event_indices: np.ndarray = field(repr=False)
    subject_ids: np.ndarray = field(repr=False)
    cluster_sizes: np.ndarray = field(repr=False)
    population_sha256: str
    feature_manifest_sha256: str

    @property
    def n_subjects(self):
        return len(self.subject_ids)

    @property
    def n_events(self):
        return len(self.event_indices)

    @property
    def metadata(self):
        role, fold = POPULATIONS[self.population]
        return {"rule_version": RULE_VERSION, "task": self.task, "split": self.split,
                "population": self.population, "role": role, "fold": fold,
                "source_subjects": self.n_subjects, "source_events": self.n_events,
                "population_sha256": self.population_sha256,
                "feature_manifest_sha256": self.feature_manifest_sha256}

    def indices_from_counts(self, patient_counts):
        """Replay compact counts; each original event repeats its cluster count.

        Counts align with sorted subject_ids and sum to the original number of
        subjects. Their event expansion need not preserve the original event N.
        """
        counts = np.asarray(patient_counts)
        if counts.ndim != 1 or len(counts) != self.n_subjects:
            raise ValueError("Patient count vector does not match the population")
        if self.n_subjects == 0:
            return np.empty(0, dtype=np.int64)
        if (counts.dtype.kind not in "iu" or (counts < 0).any()
                or (counts > self.n_subjects).any()
                or int(counts.sum(dtype=np.int64)) != self.n_subjects):
            raise ValueError("Patient counts must be nonnegative integers summing to original subject N")
        repeats = np.repeat(counts.astype(np.int64, copy=False), self.cluster_sizes)
        return np.repeat(self.event_indices, repeats)

    def draw(self, draw_id, *, seed=DEFAULT_SEED):
        """Return one independent keyed draw, reproducible in any execution order."""
        if isinstance(draw_id, bool) or not isinstance(draw_id, Integral) or not 0 <= draw_id < BOOTSTRAP_REPETITIONS:
            raise ValueError("Bootstrap draw ID must be an integer in 0..499")
        if not isinstance(seed, str) or not seed:
            raise ValueError("Bootstrap seed must be a nonempty string")
        draw_id = int(draw_id)
        key = [RULE_VERSION, seed, self.task, self.split, draw_id, self.population]
        key_digest = hashlib.sha256(_json(key)).digest()
        # Explicit little-endian words avoid architecture-dependent entropy.
        entropy = np.frombuffer(key_digest, dtype="<u4").tolist()
        rng = np.random.default_rng(np.random.SeedSequence(entropy))
        if self.n_subjects:
            sampled = rng.integers(self.n_subjects, size=self.n_subjects, dtype=np.int64)
            counts = np.bincount(sampled, minlength=self.n_subjects).astype(np.int64, copy=False)
        else:
            counts = np.empty(0, dtype=np.int64)
        indices = self.indices_from_counts(counts)
        digest = hashlib.sha256(_json([RULE_VERSION, self.population_sha256, key_digest.hex()]))
        digest.update(_array_bytes(counts))
        counts.setflags(write=False)
        indices.setflags(write=False)
        metadata = {
            "rule_version": RULE_VERSION, "task": self.task, "split": self.split,
            "population": self.population, "draw_id": draw_id, "seed": seed,
            "sampling_key_sha256": key_digest.hex(), "draw_sha256": digest.hexdigest(),
            "population_sha256": self.population_sha256,
            "feature_manifest_sha256": self.feature_manifest_sha256,
            "status": "complete" if self.n_subjects else "not_estimable",
            "reason": "" if self.n_subjects else "empty_population",
            "source_subjects": self.n_subjects, "source_events": self.n_events,
            "sampled_patient_draws": int(counts.sum()),
            "unique_sampled_subjects": int(np.count_nonzero(counts)),
            "sampled_events": len(indices), "redraws": 0,
            "sampling_unit": "subject", "event_weighting": "equal_per_repeated_event",
            "patient_count_order": "ascending_original_subject_id",
            "rng": "numpy.default_rng(SeedSequence(SHA256_little_endian_uint32))",
            "bit_generator": type(rng.bit_generator).__name__,
        }
        return ClusterDraw(indices, self.subject_ids, counts, metadata)


def build_cluster_population(dataset, split, population):
    """Build once per fixed population, without changing patient roles or folds.

    ClinicalDataset has already validated artifact provenance. This entry point
    also checks the relevant patient isolation invariants, so an inconsistent
    in-memory mask cannot quietly move another role or fold into a draw.
    """
    if np is None:
        raise RuntimeError("Patient bootstrap requires the declared NumPy dependency")
    if dataset.task not in ACTIONS or split not in SPLITS or population not in POPULATIONS:
        raise ValueError("Unknown task, split, or bootstrap population")
    subject_values = np.asarray(dataset.subject_ids)
    roles, folds = np.asarray(dataset.roles), np.asarray(dataset.folds)
    n = len(dataset.event_ids)
    if (subject_values.shape != (n,) or roles.shape != (n, len(SPLITS)) or folds.shape != (n,)
            or subject_values.dtype.kind not in "iu" or roles.dtype.kind not in "iu" or folds.dtype.kind not in "iu"):
        raise ValueError("Invalid dataset subject, role, or fold arrays")
    if ((subject_values <= 0).any() or (subject_values > 2147483647).any()
            or not np.isin(roles, tuple(ROLE_CODES.values())).all()
            or not np.isin(folds, tuple(FOLD_CODES.values())).all()):
        raise ValueError("Invalid dataset subject or role/fold code")
    subjects = subject_values.astype(np.int64, copy=False)
    split_index = SPLITS.index(split)
    if n:
        order = np.argsort(subjects, kind="stable")
        sorted_subjects = subjects[order]
        starts = np.r_[0, np.flatnonzero(sorted_subjects[1:] != sorted_subjects[:-1]) + 1]
        for values in (roles[:, split_index], folds):
            ordered = values[order]
            if np.any(np.minimum.reduceat(ordered, starts) != np.maximum.reduceat(ordered, starts)):
                raise ValueError("A patient crosses original population roles or folds")
    role, fold = POPULATIONS[population]
    mask = np.asarray(dataset.mask(split, role, fold))
    expected = (roles[:, split_index] == ROLE_CODES[role]) & (folds == FOLD_CODES[fold])
    if mask.shape != (n,) or mask.dtype.kind != "b" or not np.array_equal(mask, expected):
        raise ValueError("Population mask differs from original role/fold assignments")
    selected = np.flatnonzero(mask).astype(np.int64, copy=False)
    selected = selected[np.argsort(subjects[selected], kind="stable")]
    selected_subjects = subjects[selected]
    if len(selected):
        starts = np.r_[0, np.flatnonzero(selected_subjects[1:] != selected_subjects[:-1]) + 1]
        unique_subjects = selected_subjects[starts]
        sizes = np.diff(np.r_[starts, len(selected)]).astype(np.int64, copy=False)
    else:
        unique_subjects, sizes = np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)
    manifest_hash = dataset.provenance.get("manifest_sha256")
    if not isinstance(manifest_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", manifest_hash):
        raise ValueError("Dataset must retain its validated feature manifest hash")
    digest = hashlib.sha256(_json([RULE_VERSION, dataset.task, split, population, manifest_hash,
                                  len(selected), len(unique_subjects)]))
    for values in (selected, unique_subjects, sizes):
        digest.update(_array_bytes(values))
        values.setflags(write=False)
    return ClusterPopulation(dataset.task, split, population, selected, unique_subjects, sizes,
                             digest.hexdigest(), manifest_hash)
