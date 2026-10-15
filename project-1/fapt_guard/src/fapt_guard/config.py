"""Configuration loading.

All thresholds, weights, action catalogues and model versions live in YAML files
under ``configs/``. This module merges them into a single :class:`Config` object
and exposes a stable fingerprint so every certificate can record exactly which
configuration produced a decision.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILES = ("default.yaml", "thresholds.yaml", "optimizer.yaml", "actions.yaml")


def project_root() -> Path:
    """Repository root (``FAPT_GUARD_HOME`` overrides the source-tree location)."""
    env = os.environ.get("FAPT_GUARD_HOME")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


class Config:
    """Merged, read-mostly configuration with dotted-path access."""

    def __init__(self, data: dict[str, Any], root: Path):
        self.data = data
        self.root = root

    # -- access -----------------------------------------------------------
    def get(self, path: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in path.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def __getitem__(self, path: str) -> Any:
        value = self.get(path, _MISSING)
        if value is _MISSING:
            raise KeyError(path)
        return value

    def path(self, rel: str) -> Path:
        """Resolve a repository-relative path."""
        p = Path(rel)
        return p if p.is_absolute() else self.root / p

    def with_overrides(self, overrides: dict[str, Any]) -> "Config":
        """Return a copy with dotted-path overrides applied (used by dashboard sliders & benchmarks)."""
        data = copy.deepcopy(self.data)
        for dotted, value in overrides.items():
            node = data
            parts = dotted.split(".")
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            node[parts[-1]] = value
        return Config(data, self.root)

    # -- provenance of decisions -----------------------------------------
    def fingerprint(self) -> str:
        canonical = json.dumps(self.data, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def simulation_mode(self) -> bool:
        return bool(self.get("runtime.simulation_mode", True))

    @property
    def seed(self) -> int:
        return int(self.get("project.random_seed", 1337))

    def model_versions(self) -> dict[str, str]:
        models = self.get("models", {}) or {}
        out = {}
        for name, spec in models.items():
            if isinstance(spec, dict):
                out[name] = spec.get("version") or spec.get("baseline_version") or "unknown"
        return out


_MISSING = object()


def load_config(config_dir: str | Path | None = None, overrides: dict[str, Any] | None = None) -> Config:
    root = project_root()
    cdir = Path(config_dir) if config_dir else root / "configs"
    data: dict[str, Any] = {}
    for name in CONFIG_FILES:
        f = cdir / name
        if f.exists():
            with open(f, "r", encoding="utf-8") as fh:
                data = _deep_merge(data, yaml.safe_load(fh) or {})
    cfg = Config(data, root)
    if overrides:
        cfg = cfg.with_overrides(overrides)
    return cfg


def set_global_seed(seed: int) -> None:
    """Fix random seeds for reproducibility (numpy / random / torch when present)."""
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:  # pragma: no cover
        pass
    try:  # pragma: no cover - optional dependency
        import torch

        torch.manual_seed(seed)
    except Exception:
        pass
