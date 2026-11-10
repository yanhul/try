"""Make the pinned AIOS checkout importable as ``core`` (fail closed).

Resolution order matches ``engine/aios_boundary.py``: an explicit
``AIOS_ROOT`` / ``AIOS_SOURCE`` wins; otherwise an AIOS checkout already on
``PYTHONPATH`` is used. Import fails loudly if neither provides AIOS.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path


def ensure_aios_importable() -> Path:
    configured = os.environ.get("AIOS_ROOT") or os.environ.get("AIOS_SOURCE")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not (root / "core" / "runtime.py").is_file():
            raise ImportError(f"AIOS_ROOT does not contain core/runtime.py: {root}")
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
    core = importlib.import_module("core")
    location = Path(core.__file__).resolve().parents[1]
    if configured and location != Path(configured).expanduser().resolve():
        raise ImportError(f"'core' resolved to {location}, not the pinned AIOS_ROOT")
    if not (location / "core" / "effect_authority.py").is_file():
        raise ImportError(f"'core' at {location} is not an AIOS authority checkout")
    authority = importlib.import_module("core.effect_authority")
    for required in ("claim_execution", "ExecutionClaimRejected", "mutation_lock"):
        if not hasattr(authority, required):
            raise ImportError(
                f"pinned AIOS at {location} lacks core.effect_authority.{required}; "
                "the atomic execution-claim boundary is required (fail closed)")
    return location


AIOS_LOCATION = ensure_aios_importable()

__all__ = ["AIOS_LOCATION", "ensure_aios_importable"]
