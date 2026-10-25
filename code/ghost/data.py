"""Loaders for the participant-facing CSV files in dataset/."""
from __future__ import annotations

import csv
from pathlib import Path

from .config import DATASET


def _read(path: Path) -> list[dict[str, str]]:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_requests(sample: bool = False) -> list[dict[str, str]]:
    name = "sample_deletion_requests.csv" if sample else "deletion_requests.csv"
    return _read(DATASET / name)


def load_identities() -> list[dict[str, str]]:
    return _read(DATASET / "user_identities.csv")


def load_audit_log() -> list[dict[str, str]]:
    return _read(DATASET / "user_audit_log.csv")


def load_activity() -> list[dict[str, str]]:
    return _read(DATASET / "system_activity.csv")


def load_rules() -> list[dict[str, str]]:
    return _read(DATASET / "deletion_rules.csv")


def load_manifest() -> list[dict[str, str]]:
    return _read(DATASET / "evidence_files.csv")


def load_expected(sample: bool = True) -> dict[str, dict[str, str]]:
    rows = _read(DATASET / "sample_output.csv")
    return {r["case_id"]: r for r in rows}
