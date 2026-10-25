"""Paths and constants shared by every module."""
from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET = REPO_ROOT / "dataset"
EVIDENCE_DIR = DATASET / "evidence"
CACHE_DIR = REPO_ROOT / ".cache"
OUTPUT_CSV = REPO_ROOT / "output.csv"

MODEL = "claude-haiku-5-5"
API_KEY_ENV = "CLAIM_AGENT_ANTHROPIC_KEY"

# claude-haiku-5-5 list price for prompts under 100K tokens (USD per million tokens).
PRICE_IN_PER_MTOK = float(os.environ.get("GHOST_PRICE_IN_PER_MTOK", "0.10"))
PRICE_OUT_PER_MTOK = float(os.environ.get("GHOST_PRICE_OUT_PER_MTOK", "0.50"))
